"""
The dummy device is a virtual device that is developed as a demonstration of how an external package, that delivers a
device interface for the CGSE, can be implemented.

The simulator listens on the Ethernet socket port number 5555, unless another port number is specified in the
Settings file under the section 'DUMMY DEVICE'.

The following commands are implemented:

- *IDN? — returns identification of the device: Manufacturer, Model, Serial Number, Firmware version
- *RST — reset the instrument
- *CLS — clear
- SYSTem:TIME year, month, day, hour, minute, second — set the date/time
- SYSTem:TIME? — returns the current date/time
- info — returns a string containing brand name, model name, version, ...
- get_value — returns a measurement from the simulated temperature
"""

import contextlib
import datetime
import multiprocessing.process
import re
import select
import socket
import sys

import typer
from egse.log import logging
from egse.device import DeviceConnectionError
from egse.settings import Settings
from egse.system import SignalCatcher
from egse.system import type_name

from cgse_dummy.sim_data import SimulatedTemperature

logger = logging.getLogger("egse.dummy")

_VERSION = "0.0.2"

device_settings = Settings.load("DUMMY DEVICE")
cs_settings = Settings.load("DUMMY CS")

hostname = cs_settings.get("HOSTNAME", "localhost")
port = cs_settings.get("PORT", 5555)

device_time = datetime.datetime.now(datetime.timezone.utc)
reference_time = device_time
error_msg = ""

sensor_1 = SimulatedTemperature()

app = typer.Typer(help=f"{device_settings.BRAND} {device_settings.MODEL} Simulator")


def create_datetime(year, month, day, hour, minute, second):
    global device_time, reference_time
    device_time = datetime.datetime(
        year, month, day, hour, minute, second, tzinfo=datetime.timezone.utc
    )
    reference_time = datetime.datetime.now(datetime.timezone.utc)


def nothing():
    return None


def set_time(year, month, day, hour, minute, second):
    print(f"TIME {year}, {month}, {day}, {hour}, {minute}, {second}")
    create_datetime(
        int(year), int(month), int(day), int(hour), int(minute), int(second)
    )


def get_time():
    current_device_time = device_time + (
        datetime.datetime.now(datetime.timezone.utc) - reference_time
    )
    msg = current_device_time.strftime("%a %b %d %H:%M:%S %Y")
    print(f":SYST:TIME? {msg = }")
    return msg


def beep(a, b):
    print(f"BEEP {a=}, {b=}")


def reset():
    print("RESET")


def clear():
    """Clear all status data structures in the device."""
    print("CLEAR")


def get_value():
    _, temperature = next(sensor_1)
    return temperature


COMMAND_ACTIONS_RESPONSES = {
    "*IDN?": (
        None,
        f"{device_settings.BRAND}, {device_settings.MODEL}, {device_settings.SERIAL_NUMBER}, {_VERSION}",
    ),
    "*RST": (reset, None),
    "*CLS": (clear, None),
    "info": (
        None,
        f"{device_settings.BRAND}, MODEL {device_settings.MODEL}, {_VERSION}, SIMULATOR",
    ),
    "get_value": (None, get_value),
}


COMMAND_PATTERNS_ACTIONS_RESPONSES = {
    r":?\*RST": (reset, None),
    r":?SYST(?:em)*:TIME (\d+), (\d+), (\d+), (\d+), (\d+), (\d+)": (set_time, None),
    r":?SYST(?:em)*:TIME\?": (nothing, get_time),
    r":?SYST(?:em)*:BEEP(?:er)* (\d+), (\d+(?:\.\d+)?)": (beep, None),
}


def process_command(command_string: str) -> str:
    global COMMAND_ACTIONS_RESPONSES
    global COMMAND_PATTERNS_ACTIONS_RESPONSES

    logger.debug(f"{command_string=}")

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
                logger.debug(f"{match=}, {match.groups()}")
                action, response = value
                logger.debug(f"{action=}, {response=}")
                action and action(*match.groups())
                return error_msg or (
                    response
                    if isinstance(response, str) or response is None
                    else response()
                )
        return f"ERROR: unknown command string: {command_string}"


def run_simulator():
    """
    Raises:
        OSError: when the simulator is already running.
    """
    global error_msg

    multiprocessing.current_process().name = "dummy_sim"

    logger.info(f"Starting the {device_settings.MODEL} Simulator")

    killer = SignalCatcher()

    timeout = 2.0

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind((hostname, port))
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
                logger.info(f"Accepted connection from {addr}")
                conn.sendall(
                    f"This is {device_settings.BRAND} {device_settings.MODEL} {_VERSION}.sim".encode()
                )
                try:
                    error_msg = ""
                    while True:
                        read_sockets, _, _ = select.select([conn], [], [], timeout)

                        if conn in read_sockets:
                            data = conn.recv(4096).decode().rstrip()
                            logger.debug(f"{data = }")
                            # Now that we use `select` I don't think the following will ever be true
                            # if not data:
                            #     logger.info("Client closed connection, accepting new connection...")
                            #     break
                            if data.strip() == "STOP":
                                logger.info("Client requested to terminate...")
                                sock.close()
                                return
                            for cmd in data.split(";"):
                                logger.debug(f"{cmd=}")
                                response = process_command(cmd.strip())
                                logger.debug(f"{response=}")
                                if response is not None:
                                    response_b = f"{response}\n".encode()
                                    logger.debug(f"write: {response_b=}")
                                    conn.sendall(response_b)

                        if killer.term_signal_received:
                            logger.info("Terminating...")
                            sock.close()
                            return
                        if killer.user_signal_received:
                            if killer.signal_name == "SIGUSR1":
                                logger.info(
                                    "SIGUSR1 is not supported by this simulator"
                                )
                            if killer.signal_name == "SIGUSR2":
                                logger.info(
                                    "SIGUSR2 is not supported by this simulator"
                                )
                            killer.clear()

                except ConnectionResetError as exc:
                    logger.info(f"ConnectionResetError: {exc}")
                except Exception as exc:
                    logger.info(f"{exc.__class__.__name__} caught: {exc.args}")


def send_request(cmd: str, _type: str = "query") -> bytes:
    from cgse_dummy.dummy_dev import Dummy

    response = None

    with Dummy(hostname=hostname, port=port) as daq_dev:
        if _type == "query":
            response = daq_dev.query(cmd)
        elif _type == "write":
            daq_dev.write(cmd)
        else:
            logger.info(f"Unknown type {_type} for send_request.")

    return response


def send_command(cmd: str) -> None:
    send_request(cmd, _type="write")


@app.command()
def start():
    try:
        run_simulator()
    except OSError as exc:
        print(f"ERROR: Caught {type_name(exc)}: {exc}", file=sys.stderr)


@app.command()
def status():
    try:
        response = send_request("*IDN?")
        print(f"{response.decode().rstrip()}")
    except DeviceConnectionError as exc:
        print(f"ERROR: Caught {type_name(exc)}: {exc}", file=sys.stderr)


@app.command()
def stop():
    try:
        response = send_request("STOP")
        print(f"{response.decode().rstrip()}")
    except DeviceConnectionError as exc:
        print(f"ERROR: Caught {type_name(exc)}: {exc}", file=sys.stderr)


if __name__ == "__main__":
    app()
