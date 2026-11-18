"""Unix Domain Socket NDJSON IPC server for streaming state to native Selene HUD."""

import asyncio
import json
import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class SeleneIPCServer:
    """Lightweight, non-blocking Unix Domain Socket server broadcasting NDJSON events to the HUD."""

    def __init__(self, socket_path: Path | str = "/tmp/selene.sock"):
        self.socket_path = Path(socket_path)
        self._server: asyncio.Server | None = None
        self._clients: set[asyncio.StreamWriter] = set()
        self._command_handler: Callable[[dict[str, Any]], Any] | None = None
        self._lock = asyncio.Lock()
        self._last_state: dict[str, Any] = {"type": "state", "state": "idle"}

    async def start(self) -> None:
        """Bind and listen on the Unix Domain Socket."""
        self.socket_path.parent.mkdir(parents=True, exist_ok=True)
        self.socket_path.unlink(missing_ok=True)

        self._server = await asyncio.start_unix_server(
            self._handle_client, path=str(self.socket_path)
        )
        logger.info("Selene IPC server listening at %s", self.socket_path)

    async def _handle_client(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        async with self._lock:
            self._clients.add(writer)
            # Send current state immediately on connection
            try:
                raw = (json.dumps(self._last_state) + "\n").encode("utf-8")
                writer.write(raw)
                await writer.drain()
            except Exception:
                pass

        try:
            while True:
                line = await reader.readline()
                if not line:
                    break
                text = line.decode("utf-8", errors="replace").strip()
                if not text:
                    continue
                try:
                    payload = json.loads(text)
                    if isinstance(payload, dict) and self._command_handler is not None:
                        res = self._command_handler(payload)
                        if asyncio.iscoroutine(res):
                            await res
                except json.JSONDecodeError:
                    pass
        except (ConnectionResetError, BrokenPipeError, asyncio.CancelledError):
            pass
        finally:
            async with self._lock:
                self._clients.discard(writer)
            try:
                writer.close()
                await writer.wait_closed()
            except Exception:
                pass

    def set_command_handler(self, handler: Callable[[dict[str, Any]], Any] | None) -> None:
        """Register a callback for inbound commands from the HUD."""
        self._command_handler = handler

    async def broadcast(self, payload: dict[str, Any]) -> None:
        """Broadcast a JSON-serializable dictionary followed by newline to all connected clients."""
        if payload.get("type") == "state":
            self._last_state = payload

        if not self._clients:
            return

        raw = (json.dumps(payload) + "\n").encode("utf-8")
        dead_clients: list[asyncio.StreamWriter] = []

        async with self._lock:
            for writer in list(self._clients):
                try:
                    writer.write(raw)
                    await writer.drain()
                except (ConnectionResetError, BrokenPipeError, OSError):
                    dead_clients.append(writer)

            for dead in dead_clients:
                self._clients.discard(dead)
                try:
                    dead.close()
                except Exception:
                    pass

    async def stop(self) -> None:
        """Gracefully close all client connections and unlink the socket."""
        async with self._lock:
            for writer in list(self._clients):
                try:
                    writer.close()
                except Exception:
                    pass
            self._clients.clear()

        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()
            self._server = None

        self.socket_path.unlink(missing_ok=True)
        logger.info("Selene IPC server stopped and socket unlinked.")
