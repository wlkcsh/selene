"""Tests for Selene Unix Domain Socket IPC server."""

import asyncio
import json
from pathlib import Path

from selene.ipc_server import SeleneIPCServer


async def test_ipc_server_broadcast_and_commands():
    sock_path = Path("/tmp/selene_test_ipc.sock")
    server = SeleneIPCServer(socket_path=sock_path)
    await server.start()

    try:
        assert sock_path.exists()

        received_commands = []

        def on_command(cmd: dict):
            received_commands.append(cmd)

        server.set_command_handler(on_command)

        # Connect client
        reader, writer = await asyncio.open_unix_connection(path=str(sock_path))

        # Read initial state on connection
        initial_line = await asyncio.wait_for(reader.readline(), timeout=2.0)
        initial_event = json.loads(initial_line.decode("utf-8"))
        assert initial_event["type"] == "state"
        assert initial_event["state"] == "idle"

        # Broadcast state change
        await server.broadcast({"type": "state", "state": "listening", "cards_due": 3})
        broadcast_line = await asyncio.wait_for(reader.readline(), timeout=2.0)
        broadcast_event = json.loads(broadcast_line.decode("utf-8"))
        assert broadcast_event["state"] == "listening"
        assert broadcast_event["cards_due"] == 3

        # Client sends command
        writer.write(b'{"cmd": "interrupt"}\n')
        await writer.drain()
        await asyncio.sleep(0.05)
        assert len(received_commands) == 1
        assert received_commands[0]["cmd"] == "interrupt"

        # Clean shutdown
        writer.close()
        await writer.wait_closed()
    finally:
        await server.stop()
        assert not sock_path.exists()
