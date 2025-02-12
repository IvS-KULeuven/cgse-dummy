"""
The control server for the dummy device.
"""
import logging
import multiprocessing
import random
import sys
import threading
import time
from functools import partial

import typer
import zmq
from egse.command import ClientServerCommand
from egse.confman import is_configuration_manager_active
from egse.control import ControlServer
from egse.control import is_control_server_active
from egse.decorators import dynamic_interface
from egse.listener import Event
from egse.listener import EventInterface
from egse.protocol import CommandProtocol
from egse.proxy import Proxy
from egse.settings import Settings
from egse.storage import TYPES
from egse.storage import is_storage_manager_active
from egse.storage import register_to_storage_manager
from egse.storage import store_housekeeping_information
from egse.storage import unregister_from_storage_manager
from egse.system import attrdict
from egse.system import format_datetime
from egse.zmq_ser import bind_address
from egse.zmq_ser import connect_address

from cgse_dummy.dummy_devif import DummyEthernetInterface

_LOGGER = logging.getLogger("cgse_dummy.dummy.cs")

cs_settings = Settings.load("DUMMY CS")
dev_settings = Settings.load("DUMMY DEVICE")

DEV_HOST = "localhost"
"""The hostname or IP address of the Dummy Device."""
DEV_PORT = dev_settings.PORT
"""The port number for the Dummy Device."""
DEV_NAME = f"Dummy Device {dev_settings.MODEL}"
"""The name used for the Dummy Device, this is used in Exceptions and in the info command."""

READ_TIMEOUT = 10.0  # seconds
"""The maximum time to wait for a socket receive command."""
WRITE_TIMEOUT = 1.0  # seconds
"""The maximum time to wait for a socket send command."""
CONNECT_TIMEOUT = 3.0  # seconds
"""The maximum time to wait for establishing a socket connect."""

# Especially DummyCommand and DummyController need to be defined in a known module
# because those objects are pickled and when de-pickled at the clients side the class
# definition must be known.

commands = attrdict(
    {
        'info': {
            'description': 'Info on the Dummy Device.',
            'response': 'handle_device_method'
        },
        'get_value': {
            'description': 'Read a value from the device.',
        },
        'handle_event': {
            'description': "Notification of an event",
            'device_method': 'handle_event',
            'cmd': '{event}',
            'response': 'handle_device_method'
        },
    }
)

app = typer.Typer(help=f"Dummy control server for the dummy device {dev_settings.MODEL}")


def is_dummy_cs_active():
    return is_control_server_active(
        endpoint=connect_address(cs_settings.PROTOCOL, cs_settings.HOSTNAME, cs_settings.COMMANDING_PORT)
    )


class DummyCommand(ClientServerCommand):
    pass


class DummyInterface:
    @dynamic_interface
    def info(self):
        ...

    @dynamic_interface
    def get_value(self, *args, **kwargs):
        ...


class DummyProxy(Proxy, DummyInterface, EventInterface):
    def __init__(
            self,
            protocol=cs_settings.PROTOCOL,
            hostname=cs_settings.HOSTNAME,
            port=cs_settings.COMMANDING_PORT,
            timeout=cs_settings.TIMEOUT
    ):
        """
        Args:
            protocol: the transport protocol [default is taken from settings file]
            hostname: location of the control server (IP address) [default is taken from settings file]
            port: TCP port on which the control server is listening for commands [default is taken from settings file]
        """
        super().__init__(connect_address(protocol, hostname, port), timeout=timeout)


class DummyController(DummyInterface, EventInterface):
    def __init__(self, control_server):
        self._cs = control_server
        self._dev = DummyEthernetInterface(DEV_HOST, DEV_PORT)
        self._dev.connect()

    def info(self) -> str:
        return self._dev.trans("info").decode().strip()

    def get_value(self) -> float:
        return float(self._dev.trans("get_value").decode().strip())

    def handle_event(self, event: Event) -> str:

        _exec_in_thread = False

        def _handle_event(_event):
            _LOGGER.info(f"An event is received, {_event=}")
            _LOGGER.info(f"CM CS active? {is_configuration_manager_active()}")
            time.sleep(5.0)
            _LOGGER.info(f"CM CS active? {is_configuration_manager_active()}")
            _LOGGER.info(f"An event is processed, {_event=}")

        if _exec_in_thread:
            # We execute this function in a daemon thread so the acknowledgment is
            # sent back immediately (the ACK means 'command received and will be
            # executed').

            retry_thread = threading.Thread(target=_handle_event, args=(event,))
            retry_thread.daemon = True
            retry_thread.start()
        else:
            # An alternative to the daemon thread is to create a scheduled task that will be executed
            # after the event is acknowledged.

            self._cs.schedule_task(partial(_handle_event, event))

        return "ACK"


class DummyProtocol(CommandProtocol):

    def __init__(self, control_server: ControlServer):
        super().__init__()
        self.control_server = control_server

        self.device_controller = DummyController(control_server)

        self.load_commands(commands, DummyCommand, DummyController)

        self.build_device_method_lookup_table(self.device_controller)

        self._count = 0

    def get_bind_address(self):
        return bind_address(self.control_server.get_communication_protocol(), self.control_server.get_commanding_port())

    def get_status(self):
        return super().get_status()

    def get_housekeeping(self) -> dict:

        # _LOGGER.debug(f"Executing get_housekeeping function for {self.__class__.__name__}.")

        self._count += 1

        # use the sleep to test the responsiveness of the control server when even this get_housekeeping function takes
        # a lot of time, i.e. up to several minutes in the case of data acquisition devices
        # import time
        # time.sleep(2.0)

        return {
            'timestamp': format_datetime(),
            'COUNT': self._count,
            'PI': 3.14159,  # just to have a constant parameter
            'Random': random.randint(0, 100),  # just to have a variable parameter
        }

    def quit(self):
        _LOGGER.info("Executing 'quit()' on DummyProtocol.")


class DummyControlServer(ControlServer):
    """
    DummyControlServer - Command and monitor dummy device controllers.

    The sever binds to the following ZeroMQ sockets:

    * a REQ-REP socket that can be used as a command server. Any client can connect and
      send a command to the dummy device controller.

    * a PUB-SUP socket that serves as a monitoring server. It will send out status
      information to all the connected clients every HK_DELAY seconds.

    """

    def __init__(self):
        multiprocessing.current_process().name = "dummy_cs"

        super().__init__()

        self.device_protocol = DummyProtocol(self)

        _LOGGER.info(
            f"Binding ZeroMQ socket to {self.device_protocol.get_bind_address()} for {self.__class__.__name__}"
        )

        self.device_protocol.bind(self.dev_ctrl_cmd_sock)

        self.poller.register(self.dev_ctrl_cmd_sock, zmq.POLLIN)

        self.set_hk_delay(cs_settings.HK_DELAY)

        from egse.confman import ConfigurationManagerProxy
        from egse.listener import EVENT_ID

        # The following import is needed because without this import, DummyProxy would be <class '__main__.DummyProxy'>
        # instead of `egse.dummy.DummyProxy` and the ConfigurationManager control server will not be able to de-pickle
        # the register message.
        from egse.dummy import DummyProxy  # noqa

        self.register_as_listener(
            proxy=ConfigurationManagerProxy,
            listener={'name': 'Dummy CS', 'proxy': DummyProxy, 'event_id': EVENT_ID.SETUP}
        )

    def get_communication_protocol(self):
        return 'tcp'

    def get_commanding_port(self):
        return cs_settings.COMMANDING_PORT

    def get_service_port(self):
        return cs_settings.SERVICE_PORT

    def get_monitoring_port(self):
        return cs_settings.MONITORING_PORT

    def get_storage_mnemonic(self):
        return "DUMMY-HK"

    def after_serve(self):
        _LOGGER.debug("After Serve: unregistering Dummy CS")

        from egse.confman import ConfigurationManagerProxy

        self.unregister_as_listener(proxy=ConfigurationManagerProxy, listener={'name': 'Dummy CS'})

    def is_storage_manager_active(self):
        return is_storage_manager_active()

    def store_housekeeping_information(self, data):
        """Send housekeeping information to the Storage manager."""

        store_housekeeping_information(origin=cs_settings.STORAGE_MNEMONIC, data=data)

    def register_to_storage_manager(self) -> None:
        register_to_storage_manager(
            origin=cs_settings.STORAGE_MNEMONIC,
            persistence_class=TYPES["CSV"],
            prep={
                "column_names": list(self.device_protocol.get_housekeeping().keys()),
                "mode": "a",
            }
        )

    def unregister_from_storage_manager(self) -> None:
        unregister_from_storage_manager(origin=cs_settings.STORAGE_MNEMONIC)


@app.command()
def start():
    """Start the dummy control server on localhost."""

    # The following import is needed because without this import, the control server and Proxy will not be able to
    # instantiate classes that are passed in ZeroMQ messages and de-pickled.
    from cgse_dummy.dummy_cs import DummyControlServer  # noqa

    try:
        control_server = DummyControlServer()
        control_server.serve()
    except KeyboardInterrupt:
        print("Shutdown requested...exiting")
    except SystemExit as exit_code:
        print(f"System Exit with code {exit_code}.")
        sys.exit(-1)
    except Exception:  # noqa
        import traceback
        traceback.print_exc(file=sys.stdout)


@app.command()
def stop():
    """Send a quit service command to the dummy control server."""
    with DummyProxy() as dummy:
        _LOGGER.info("Sending quit_server() to Dummy CS.")
        sp = dummy.get_service_proxy()
        sp.quit_server()


if __name__ == '__main__':
    app()
