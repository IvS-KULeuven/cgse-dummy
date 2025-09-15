"""
The asynchronous control server for the dummy device.
"""

import asyncio
import json
import logging
from typing import Any
from typing import Callable

import zmq
import zmq.asyncio
from egse.log import logger
from egse.system import Periodic
from egse.system import get_current_location
from egse.zmq_ser import get_port_number
from egse.zmq_ser import zmq_error_response

# When zero (0) ports will be dynamically allocated by the system
CONTROL_SERVER_DEVICE_COMMANDING_PORT = 6666  # settings.get("COMMANDING_PORT", 0)
CONTROL_SERVER_SERVICE_COMMANDING_PORT = 6667  # settings.get("SERVICE_PORT", 0)


class AsyncControlServer:
    def __init__(self):
        self.interrupted = asyncio.Event()
        self.logger = logger
        self.logger.name = "egse.async_control"

        self._tasks: list | None = None
        """The background top-level tasks that are performed by the control server."""

        self._ctx = zmq.asyncio.Context.instance()
        """Global instance of the ZeroMQ context."""

        self.device_command_port = CONTROL_SERVER_DEVICE_COMMANDING_PORT
        """The device commanding port for the control server. This will be 0 at start and dynamically assigned by the
        system."""

        self.device_command_socket = self._ctx.socket(zmq.REP)
        """Socket to handle REQ-REP device commanding pattern."""
        self.device_command_socket.bind(f"tcp://*:{self.device_command_port}")
        self.device_command_port = get_port_number(self.device_command_socket)

    async def start(self):
        self._tasks: list[asyncio.Task] = [
            asyncio.create_task(
                self.process_device_command(), name="process-device-commands"
            ),
            asyncio.create_task(self.send_status_updates(), name="send-status-updates"),
        ]

        try:
            while True:
                if self.interrupted.is_set():
                    break
                await self._check_tasks_health()
                await asyncio.sleep(1.0)
        except asyncio.CancelledError:
            self.logger.debug(
                f"Caught CancelledError on server keep-alive loop, terminating {type(self).__name__}."
            )
        finally:
            await self._cleanup_running_tasks()

    def stop(self):
        self.interrupted.set()

    async def _check_tasks_health(self):
        """Check if any tasks unexpectedly terminated."""
        for task in self._tasks:
            if task.done() and not task.cancelled():
                try:
                    # This will raise any exception that occurred in the task
                    task.result()
                except Exception as exc:
                    self.logger.error(f"Task {task.get_name()} failed: {exc}")
                    # Potentially restart the task or shut down service

    async def _cleanup_running_tasks(self):
        # Cancel all running tasks
        for task in self._tasks:
            if not task.done():
                self.logger.debug(f"Cancelling task {task.get_name()}.")
                task.cancel()

        if self._tasks:
            try:
                await asyncio.gather(*self._tasks, return_exceptions=True)
            except asyncio.CancelledError as exc:
                self.logger.debug(f"Caught {type(exc).__name__}: {exc}.")
                pass

    async def process_device_command(self):
        while True:
            if self.interrupted.is_set():
                break

            try:
                # Wait for a request with timeout to allow checking if still running
                try:
                    parts = await asyncio.wait_for(
                        self.device_command_socket.recv_multipart(), timeout=1.0
                    )
                except asyncio.TimeoutError:
                    continue

                # For commanding, we only accept simple commands as a string or a complex command with arguments as
                # JSON data. In both cases, there are only two parts in this multipart message.
                message_type, data = parts
                if message_type == b"MESSAGE_TYPE:STRING":
                    device_command = {"command": data.decode("utf-8")}
                elif message_type == b"MESSAGE_TYPE:JSON":
                    device_command = json.loads(data.decode())
                else:
                    filename, lineno, function_name = get_current_location()
                    # We have an unknown message format, send an error message back
                    message = zmq_error_response(
                        {
                            "success": False,
                            "message": f"Incorrect message type: {message_type}",
                            "metadata": {
                                "data": data.decode(),
                                "file": filename,
                                "lineno": lineno,
                                "function": function_name,
                            },
                        }
                    )
                    await self.device_command_socket.send_multipart(message)
                    continue

                self.logger.debug(f"Received request: {device_command}")

                self.logger.debug("Process the command...")
                response = await self._process_device_command(device_command)

                self.logger.debug("Send the response...")
                await self.device_command_socket.send_multipart(response)

            except asyncio.CancelledError:
                self.logger.debug("Device command handling task cancelled.")
                break

        self._cleanup_device_command_socket()

    async def _process_device_command(self, cmd: dict[str, Any]) -> list:
        command = cmd.get("command")
        if not command:
            return zmq_error_response(
                {
                    "success": False,
                    "message": "no command field provide, don't know what to do.",
                }
            )

        handlers: dict[str, Callable] = {}

        handler = handlers.get(command)
        if not handler:
            filename, lineno, function_name = get_current_location()
            return zmq_error_response(
                {
                    "success": False,
                    "message": f"Unknown command: {command}",
                    "metadata": {
                        "file": filename,
                        "lineno": lineno,
                        "function": function_name,
                    },
                }
            )

        return await handler(cmd)

    def _cleanup_device_command_socket(self):
        self.logger.debug("Cleaning up device command sockets.")
        if self.device_command_socket:
            self.device_command_socket.close(linger=0)
        self.device_command_socket = None

    async def send_status_updates(self):
        """
        Send status information about the control server and the device connection to the monitoring channel.
        """

        async def status():
            self.logger.info(f"Sending status updates.")
            await asyncio.sleep(
                0.5
            )  # ideally, should not be larger than periodic interval

        try:
            periodic = Periodic(interval=1.0, callback=status)
            periodic.start()

            await self.interrupted.wait()

        except asyncio.CancelledError:
            self.logger.debug(
                "Caught CancelledError on status updates keep-alive loop."
            )


async def control_server_test():
    # First start the control server as a background task.
    server = AsyncControlServer()
    server_task = asyncio.create_task(server.start())

    # Give the control server the time to start up
    await asyncio.sleep(0.5)

    # Now create a control client that will connect to the above server.
    client = await AsyncControlClient.create(service_type="async-control-server")
    client.connect()

    # Sleep some time, so we can see the control server in action, e.g. status reports, housekeeping, etc
    await asyncio.sleep(5.0)

    response = await client.ping()
    print(f"ping: {response = }")

    response = await client.info()
    print(f"info: {response = }")

    # info is a service command and not a device command, so this will fail.
    response = await client.do({"command": "info"})
    print(f"command info: {response = }")

    is_active = await is_control_server_active(service_type="async-control-server")
    print(f"Server status: {'active' if is_active else 'unreachable'}")

    print("Terminating the server.")
    response = await client.terminate()
    print(f"terminate: {response = }")

    client.disconnect()

    is_active = await is_control_server_active(service_type="async-control-server")
    print(f"Server status: {'active' if is_active else 'unreachable'}")

    await server_task

    is_active = await is_control_server_active(service_type="async-control-server")
    print(f"Server status: {'active' if is_active else 'unreachable'}")


if __name__ == "__main__":
    logging.captureWarnings(True)

    try:
        # asyncio.run(periodic_test())
        asyncio.run(control_server_test())
    except KeyboardInterrupt:
        print("Caught KeyboardInterrupt, terminating.")
