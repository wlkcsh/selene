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
        writer.write(b'{"cmd": "text", "text": "hello from app"}\n')
        writer.write(b'{"cmd": "ptt_start"}\n')
        writer.write(b'{"cmd": "set_mode", "mode": "hands_free"}\n')
        writer.write(b'{"cmd": "fetch_due_cards", "limit": 10}\n')
        writer.write(b'{"cmd": "grade_card", "card_id": 1, "quality": 4}\n')
        await writer.drain()
        await asyncio.sleep(0.05)
        assert len(received_commands) == 6
        assert received_commands[0]["cmd"] == "interrupt"
        assert received_commands[1]["cmd"] == "text"
        assert received_commands[2]["cmd"] == "ptt_start"
        assert received_commands[3]["cmd"] == "set_mode"
        assert received_commands[3]["mode"] == "hands_free"
        assert received_commands[4]["cmd"] == "fetch_due_cards"
        assert received_commands[5]["cmd"] == "grade_card"

        # Clean shutdown
        writer.close()
        await writer.wait_closed()
    finally:
        await server.stop()
        assert not sock_path.exists()
