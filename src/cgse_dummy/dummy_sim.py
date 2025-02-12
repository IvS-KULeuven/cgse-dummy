"""
The dummy device is a virtual device that is developed as a demonstration of how an external package, that delivers a
device interface for the CGSE, can be implemented.

The simulator listens on the Ethernet socket port number 5555, unless another port number is specified in the
Settings file under the section 'DUMMY DEVICE'.

The following commands are implemented:

- *IDN? — request identification of the device

"""

import contextlib
import datetime
import logging
import re
import select
import socket
import sys

import typer
from egse.device import DeviceConnectionError
from egse.settings import Settings
from egse.system import SignalCatcher
from egse.randomwalk import RandomWalk


logging.basicConfig(level=logging.INFO)

_LOGGER = logging.getLogger("cgse_dummy.dummy.sim")
_VERSION = "0.0.1"

DEVICE_SETTINGS = Settings.load("DUMMY DEVICE")
CS_SETTINGS = Settings.load("DUMMY CS")

try:
    HOSTNAME = CS_SETTINGS.HOSTNAME
except AttributeError:
    HOSTNAME = "localhost"

try:
    PORT = CS_SETTINGS.PORT
except AttributeError:
    PORT = 5555

device_time = datetime.datetime.now(datetime.timezone.utc)
reference_time = device_time
error_msg = ""

sensor_1 = RandomWalk()

app = typer.Typer(help=f"{DEVICE_SETTINGS.BRAND} {DEVICE_SETTINGS.MODEL} Simulator")


def create_datetime(year, month, day, hour, minute, second):
    global device_time, reference_time
    device_time = datetime.datetime(year, month, day, hour, minute, second, tzinfo=datetime.timezone.utc)
    reference_time = datetime.datetime.now(datetime.timezone.utc)


def nothing():
    return None


def set_time(year, month, day, hour, minute, second):
    print(f"TIME {year}, {month}, {day}, {hour}, {minute}, {second}")
    create_datetime(int(year), int(month), int(day), int(hour), int(minute), int(second))


def get_time():
    current_device_time = device_time + (datetime.datetime.now(datetime.timezone.utc) - reference_time)
    msg = current_device_time.strftime("%a %b %d %H:%M:%S %Y")
    print(f":SYST:TIME? {msg = }")
    return msg


def beep(a, b):
    print(f"BEEP {a=}, {b=}")


def reset():
    print("RESET")


def clear():
    print("CLEAR")


def get_value():
    return next(sensor_1)


COMMAND_ACTIONS_RESPONSES = {
    "*IDN?": (None, f"{DEVICE_SETTINGS.BRAND}, MODEL {DEVICE_SETTINGS.MODEL}, SIMULATOR"),
    "*RST": (reset, None),
    "*CLS": (clear, None),

    "info": (None, f"{DEVICE_SETTINGS.BRAND}, MODEL {DEVICE_SETTINGS.MODEL}, SIMULATOR"),
    "get_value": (None, get_value),
}


COMMAND_PATTERNS_ACTIONS_RESPONSES = {
    r":?\*RST": (reset, None),
    r":?SYST(?:em)*:TIME (\d+), (\d+), (\d+), (\d+), (\d+), (\d+)": (set_time, None),
    r":?SYST(?:em)*:TIME\? 1": (nothing, get_time),
    r":?SYST(?:em)*:BEEP(?:er)* (\d+), (\d+(?:\.\d+)?)": (beep, None),
}


def process_command(command_string: str) -> str:

    global COMMAND_ACTIONS_RESPONSES
    global COMMAND_PATTERNS_ACTIONS_RESPONSES

    # LOGGER.debug(f"{command_string=}")

    try:
        action, response = COMMAND_ACTIONS_RESPONSES[command_string]
        action and action()
        if error_msg:
            return error_msg
        else:
            return response if isinstance(response, str) else response()
    except KeyError:
        # try to match with a value
        for key, value in COMMAND_PATTERNS_ACTIONS_RESPONSES.items():
            if match := re.match(key, command_string):
                # LOGGER.debug(f"{match=}, {match.groups()}")
                action, response = value
                # LOGGER.debug(f"{action=}, {response=}")
                action and action(*match.groups())
                return error_msg or (response if isinstance(response, str) or response is None else response())
        return f"ERROR: unknown command string: {command_string}"


def run_simulator():
    """
    Raises:
        OSError: when the simulator is already running.
    """
    global error_msg

    _LOGGER.info(f"Starting the {DEVICE_SETTINGS.MODEL} Simulator")

    killer = SignalCatcher()

    timeout = 2.0

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind((HOSTNAME, PORT))
        sock.listen()
        sock.settimeout(timeout)
        while True:
            while True:
                with contextlib.suppress(socket.timeout):
                    conn, addr = sock.accept()
                    break
                if killer.term_signal_received:
                    return
            with conn:
                _LOGGER.info(f'Accepted connection from {addr}')
                conn.sendall(f'This is {DEVICE_SETTINGS.BRAND} {DEVICE_SETTINGS.MODEL} {_VERSION}.sim'.encode())
                try:
                    error_msg = ""
                    while True:

                        read_sockets, _, _ = select.select([conn], [], [], timeout)

                        if conn in read_sockets:
                            data = conn.recv(4096).decode().rstrip()
                            _LOGGER.debug(f"{data = }")
                            # Now that we use `select` I don't think the following will ever be true
                            # if not data:
                            #     _LOGGER.info("Client closed connection, accepting new connection...")
                            #     break
                            if data.strip() == "STOP":
                                _LOGGER.info("Client requested to terminate...")
                                sock.close()
                                return
                            for cmd in data.split(';'):
                                response = process_command(cmd.strip())
                                if response is not None:
                                    response_b = f"{response}\n".encode()
                                    _LOGGER.debug(f"write: {response_b = }")
                                    conn.sendall(response_b)

                        if killer.term_signal_received:
                            _LOGGER.info("Terminating...")
                            sock.close()
                            return
                        if killer.user_signal_received:
                            if killer.signal_name == "SIGUSR1":
                                _LOGGER.info("SIGUSR1 is not supported by this simulator")
                            if killer.signal_name == "SIGUSR2":
                                _LOGGER.info("SIGUSR2 is not supported by this simulator")
                            killer.clear()

                except ConnectionResetError as exc:
                    _LOGGER.info(f"ConnectionResetError: {exc}")
                except Exception as exc:
                    _LOGGER.info(f"{exc.__class__.__name__} caught: {exc.args}")


def send_request(cmd: str) -> bytes:

    from cgse_dummy.dummy_devif import DummyEthernetInterface

    daq_dev = DummyEthernetInterface(hostname=HOSTNAME, port=PORT)
    daq_dev.connect()

    response = daq_dev.query(cmd)

    daq_dev.disconnect()

    return response


@app.command()
def start():
    try:
        run_simulator()
    except OSError as exc:
        print(f"ERROR: Caught {exc.__class__.__name__}: {exc}", file=sys.stderr)


@app.command()
def status():
    try:
        response = send_request("*IDN?")
        print(f"{response.decode().rstrip()}")
    except DeviceConnectionError as exc:
        print(f"ERROR: Caught {exc.__class__.__name__}: {exc}", file=sys.stderr)


@app.command()
def stop():
    try:
        response = send_request("STOP")
        print(f"{response.decode().rstrip()}")
    except DeviceConnectionError as exc:
        print(f"ERROR: Caught {exc.__class__.__name__}: {exc}", file=sys.stderr)


if __name__ == '__main__':
    app()
