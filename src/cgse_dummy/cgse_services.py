# An example plugin with a dummy device driver
#
import subprocess
import sys
import textwrap
from pathlib import Path

import rich
import typer

dummy = typer.Typer(
    name="dummy",
    help=textwrap.dedent(
        """DUMMY Data Acquisition Unit
        
        This is a simple simulator of a data acquisition device that can be used to monitor
        a number of sensors.         
        """
    ),
    no_args_is_help=True
)


@dummy.command(name="start")
def start_dummy():
    """Start the dummy service, dummy_cs."""
    rich.print("Starting service dummy_cs..")

    out = open(Path('~/.dummy_cs.start.out').expanduser(), 'w')

    subprocess.Popen(
        [sys.executable, '-m', 'cgse_dummy.dummy_cs', 'start'],
        stdout=out, stderr=out, stdin=subprocess.DEVNULL,
        close_fds=True
    )


@dummy.command(name="stop")
def stop_dummy():
    """Stop the dummy service, dummy_cs."""
    rich.print("Terminating service dummy_cs..")

    out = open(Path('~/.dummy_cs.stop.out').expanduser(), 'w')

    subprocess.Popen(
        [sys.executable, '-m', 'cgse_dummy.dummy_cs', 'stop'],
        stdout=out, stderr=out, stdin=subprocess.DEVNULL,
        close_fds=True
    )


@dummy.command(name="status")
def status_dummy():
    """Print the status information from the dummy service, dummy_cs."""
    rich.print("Status information from the dummy service not implemented yet..")


@dummy.command(name="start-sim")
def start_dummy_sim():
    """Start the dummy device Simulator."""
    rich.print("Starting service DUMMY Simulator")

    out = open(Path('~/.dummy_sim.start.out').expanduser(), 'w')

    subprocess.Popen(
        [sys.executable, '-m', 'cgse_dummy.dummy_sim', 'start'],
        stdout=out, stderr=out, stdin=subprocess.DEVNULL,
        close_fds=True
    )


@dummy.command(name="stop-sim")
def stop_dummy_sim():
    """Stop the dummy device Simulator."""
    rich.print("Terminating the DUMMY simulator.")

    out = open(Path('~/.dummy_sim.stop.out').expanduser(), 'w')

    subprocess.Popen(
        [sys.executable, '-m', 'cgse_dummy.dummy_sim', 'stop'],
        stdout=out, stderr=out, stdin=subprocess.DEVNULL,
        close_fds=True
    )


@dummy.command(name="status-sim")
def status_dummy_sim():
    """Print status information on the dummy device simulator."""

    proc = subprocess.Popen(
        [sys.executable, '-m', 'cgse_dummy.dummy_sim', 'status'],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, stdin=subprocess.DEVNULL
    )

    stdout, stderr = proc.communicate()

    rich.print(stdout.decode(), end='')
    if stderr:
        rich.print(stderr.decode())


if __name__ == '__main__':
    dummy()
