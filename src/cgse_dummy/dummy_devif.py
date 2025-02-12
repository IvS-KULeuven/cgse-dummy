"""
The device driver for the dummy device.

The device driver has an Ethernet interface that listens to the port specified in the Settings file in the section
'DUMMY DEVICE'.

"""
__all__ = [
    "DummyEthernetInterface",
]

import logging
import socket
import time

from egse.device import DeviceConnectionError
from egse.device import DeviceConnectionInterface
from egse.device import DeviceError
from egse.device import DeviceTimeoutError
from egse.device import DeviceTransport
from egse.settings import Settings

logging.basicConfig(level=logging.DEBUG)

_LOGGER = logging.getLogger("cgse_dummy.dummy.devif")
_VERSION = "0.0.1"

IDENTIFICATION_QUERY = "*IDN?"

DEVICE_SETTINGS = Settings.load("DUMMY DEVICE")
CS_SETTINGS = Settings.load("DUMMY CS")

READ_TIMEOUT = DEVICE_SETTINGS.TIMEOUT  # [s], can be smaller than timeout (for Proxy) (e.g. 1s)


class DummyEthernetInterface(DeviceConnectionInterface, DeviceTransport):
    """
    Defines the low-level interface to the DUMMY Instruments DAQ-1234 Simulator.

    Args:
        - hostname (str): the IP address or hostname of the device, if None, this is taken from the Settings
        - port (int): the port number for the device connection, if None, this will be taken from the Settings

    """

    def __init__(self, hostname: str = None, port: int = None):
        """ Initialisation of an Ethernet interface for the DAQ-1234.

        Args:
            hostname(str): Hostname to which to open a socket
            port (int): Port to which to open a socket
        """

        super().__init__()

        self.hostname = DEVICE_SETTINGS.HOSTNAME if hostname is None else hostname
        self.port = DEVICE_SETTINGS.PORT if port is None else port
        self.sock = None

        self.is_connection_open = False

    def connect(self) -> None:
        """
        Connects the device.

        If the connection is already open, a warning will be issued and the function returns.

        Raises:
            DeviceConnectionError: When the connection could not be established. Check the logging messages for more
                                   details.

            DeviceTimeoutError: When the connection timed out.

            ValueError: When hostname or port number are not provided.
        """

        # Sanity checks

        if self.is_connection_open:
            _LOGGER.warning(f"{DEVICE_SETTINGS.MODEL}: trying to connect to an already connected socket.")
            return

        if self.hostname in (None, ""):
            raise ValueError(f"{DEVICE_SETTINGS.MODEL}: hostname is not initialized.")

        if self.port in (None, 0):
            raise ValueError(f"{DEVICE_SETTINGS.MODEL}: port number is not initialized.")

        # Create a new socket instance

        try:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            # The following lines are to experiment with blocking and timeout, but there is no need.
            # self.sock.setblocking(1)
            # self.sock.settimeout(3)
        except socket.error as e_socket:
            raise DeviceConnectionError(DEVICE_SETTINGS.MODEL, "Failed to create socket.") from e_socket

        # Attempt to establish a connection to the remote host

        # FIXME: Socket shall be closed on exception?

        # We set a timeout of 3s before connecting and reset to None (=blocking) after the `connect` method has been
        # called. This is because when no device is available, e.g. during testing, the timeout will take about
        # two minutes, which is way too long. It needs to be evaluated if this approach is acceptable and not causing
        # problems during production.

        try:
            _LOGGER.debug(f'Connecting a socket to host "{self.hostname}" using port {self.port}')
            self.sock.settimeout(3)
            self.sock.connect((self.hostname, self.port))
            self.sock.settimeout(None)
        except ConnectionRefusedError as exc:
            raise DeviceConnectionError(
                DEVICE_SETTINGS.MODEL, f"Connection refused to {self.hostname}:{self.port}."
            ) from exc
        except TimeoutError as exc:
            raise DeviceTimeoutError(
                DEVICE_SETTINGS.MODEL, f"Connection to {self.hostname}:{self.port} timed out."
            ) from exc
        except socket.gaierror as exc:
            raise DeviceConnectionError(
                DEVICE_SETTINGS.MODEL, f"Socket address info error for {self.hostname}"
            ) from exc
        except socket.herror as exc:
            raise DeviceConnectionError(
                DEVICE_SETTINGS.MODEL, f"Socket host address error for {self.hostname}"
            ) from exc
        except OSError as exc:
            raise DeviceConnectionError(DEVICE_SETTINGS.MODEL, f"OSError caught ({exc}).") from exc

        self.is_connection_open = True

        # Check that we are connected to the controller by issuing the "VERSION" or
        # "*ISDN?" query. If we don't get the right response, then disconnect automatically.

        if not self.is_connected():
            raise DeviceConnectionError(
                DEVICE_SETTINGS.MODEL, "Device is not connected, check logging messages for the cause."
            )

    def disconnect(self) -> None:
        """
        Disconnects from the Ethernet connection.

        Raises:
            DeviceConnectionError when the socket could not be closed.
        """

        try:
            if self.is_connection_open:
                _LOGGER.debug(f"Disconnecting from {self.hostname}")
                self.sock.close()
                self.is_connection_open = False
        except Exception as e_exc:
            raise DeviceConnectionError(
                DEVICE_SETTINGS.MODEL, f"Could not close socket to {self.hostname}") from e_exc

    def reconnect(self):
        """ Reconnects to the device controller.

        Raises:
            ConnectionError when the device cannot be reconnected for some reason.
        """

        if self.is_connection_open:
            self.disconnect()
        self.connect()

    def is_connected(self) -> bool:
        """
        Checks if the device is connected.

        This will send a query for the device identification and validate the answer.

        Returns:
            True is the device is connected and answered with the proper IDN; False otherwise.
        """

        if not self.is_connection_open:
            return False

        try:
            idn = self.query(IDENTIFICATION_QUERY).decode()
        except DeviceError as exc:
            _LOGGER.exception(exc)
            _LOGGER.error("Most probably the client connection was closed. Disconnecting...")
            self.disconnect()
            return False

        if DEVICE_SETTINGS.MODEL not in idn:
            _LOGGER.error(
                f'Device did not respond correctly to a "{IDENTIFICATION_QUERY}" command, response={idn}. '
                f"Disconnecting..."
            )
            self.disconnect()
            return False

        return True

    def write(self, command: str):
        """
        Sends a single command to the device controller without waiting for a response.

        Args:
            command (str): Command to send to the controller

        Raises:
            DeviceConnectionError when the command could not be sent due to a communication problem.
            DeviceTimeoutError when the command could not be sent due to a timeout.
        """

        try:
            command += "\n" if not command.endswith("\n") else ""

            self.sock.sendall(command.encode())

        except socket.timeout as e_timeout:
            raise DeviceTimeoutError(DEVICE_SETTINGS.MODEL, "Socket timeout error") from e_timeout
        except socket.error as e_socket:
            # Interpret any socket-related error as a connection error
            raise DeviceConnectionError(DEVICE_SETTINGS.MODEL, "Socket communication error.") from e_socket
        except AttributeError:
            if not self.is_connection_open:
                msg = "The DAQ6510 is not connected, use the connect() method."
                raise DeviceConnectionError(DEVICE_SETTINGS.MODEL, msg)
            raise

    def trans(self, command: str) -> bytes:
        """
        Sends a single command to the device controller and block until a response from the controller.

        This is seen as a transaction.

        Args:
            command (str): Command to send to the controller

        Returns:
            Either a bytes object returned by the controller (on success), or an error message (on failure).

        Raises:
            DeviceConnectionError when there was an I/O problem during communication with the controller.
            DeviceTimeoutError when there was a timeout in either sending the command or receiving the response.
        """

        try:
            # Attempt to send the complete command

            command += "\n" if not command.endswith("\n") else ""

            self.sock.sendall(command.encode())

            # wait for, read and return the response from HUBER (will be at most TBD chars)

            response = self.read()

            return response

        except ConnectionError as exc:
            raise DeviceConnectionError(DEVICE_SETTINGS.MODEL, "Connection error.") from exc
        except socket.timeout as e_timeout:
            raise DeviceTimeoutError(DEVICE_SETTINGS.MODEL, "Socket timeout error") from e_timeout
        except socket.error as e_socket:
            # Interpret any socket-related error as an I/O error
            raise DeviceConnectionError(DEVICE_SETTINGS.MODEL, "Socket communication error.") from e_socket
        except AttributeError:
            if not self.is_connection_open:
                raise DeviceConnectionError(
                    DEVICE_SETTINGS.MODEL, "Device not connected, use the connect() method."
                )
            raise

    def read(self) -> bytes:
        """
        Reads from the device buffer.

        Returns:
            The content of the device buffer.
        """

        n_total = 0
        buf_size = 2048

        data = b''

        # Set a timeout of READ_TIMEOUT to the socket.recv

        saved_timeout = self.sock.gettimeout()
        self.sock.settimeout(READ_TIMEOUT)

        try:
            for idx in range(100):
                time.sleep(0.001)  # Give the device time to fill the buffer
                data = self.sock.recv(buf_size)
                n = len(data)
                n_total += n
                if n < buf_size:
                    break
        except TimeoutError as exc:
            _LOGGER.warning(f"Socket timeout error for {self.hostname}:{self.port}: {exc}")
            return b"\r\n"
        finally:
            self.sock.settimeout(saved_timeout)

        # _LOGGER.debug(f"Total number of bytes received is {n_total}, idx={idx}")

        return data
