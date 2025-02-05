# An example plugin with a dummy device driver
#
import subprocess
import sys
from pathlib import Path

import rich
import typer

dummy = typer.Typer(
    name="dummy",
    help="DUMMY Data Acquisition Unit",
    no_args_is_help=True
)


@dummy.command(name="start")
def start_dummy():
    """Start the dummy service, dummy_cs."""
    rich.print("Starting service dummy not implemented yet..")


@dummy.command(name="stop")
def stop_dummy():
    """Stop the dummy service, dummy_cs."""
    rich.print("Terminating service dummy not implemented yet..")


@dummy.command(name="status")
def status_dummy():
    """Print the status information from the dummy service, dummy_cs."""
    rich.print("Status information from the dummy service not implemented yet..")


@dummy.command(name="start-sim")
def start_dummy_sim():
    """Start the dummy device Simulator."""
    rich.print("Starting service DUMMY Simulator")

    out = open(Path('~/.dummy_sim.start.out').expanduser(), 'w')
    err = open(Path('~/.dummy_sim.start.err').expanduser(), 'w')

    subprocess.Popen(
        [sys.executable, '-m', 'cgse_dummy.dummy_sim', 'start'],
        stdout=out, stderr=err, stdin=subprocess.DEVNULL,
        close_fds=True
    )


@dummy.command(name="stop-sim")
def stop_dummy_sim():
    """Stop the dummy device Simulator."""
    rich.print("Terminating the DUMMY simulator.")

    out = open(Path('~/.dummy_sim.stop.out').expanduser(), 'w')
    err = open(Path('~/.dummy_sim.stop.err').expanduser(), 'w')

    subprocess.Popen(
        [sys.executable, '-m', 'cgse_dummy.dummy_sim', 'stop'],
        stdout=out, stderr=err, stdin=subprocess.DEVNULL,
        close_fds=True
    )


@dummy.command(name="status-sim")
def status_dummy_sim():
    """Print status information on the dummy device simulator."""

    err = open(Path('~/.dummy_sim.status.err').expanduser(), 'w')

    proc = subprocess.Popen(
        [sys.executable, '-m', 'cgse_dummy.dummy_sim', 'status'],
        stdout=subprocess.PIPE, stderr=err, stdin=subprocess.DEVNULL
    )

    stdout, _ = proc.communicate()

    rich.print(stdout.decode(), end='')


if __name__ == '__main__':
    dummy()
