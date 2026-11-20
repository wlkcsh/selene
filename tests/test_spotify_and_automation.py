"""Unit tests for SpotifyResolver, native automation RPC, and media tools."""

import asyncio
import uuid
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from selene.ipc_server import SeleneIPCServer
from selene.mac_tools import build_jarvis_tools, control_media
from selene.spotify_resolver import SpotifyResolver


@pytest.mark.asyncio
async def test_spotify_resolver_empty_query():
    resolver = SpotifyResolver()
    assert await resolver.find_track("") is None
    assert await resolver.find_track("   ") is None


@pytest.mark.asyncio
async def test_spotify_resolver_itunes_fallback():
    resolver = SpotifyResolver()

    mock_resp = MagicMock()
    mock_resp.json.return_value = {
        "resultCount": 1,
        "results": [
            {
                "trackName": "Starboy (feat. Daft Punk)",
                "artistName": "The Weeknd",
            }
        ],
    }
    mock_resp.raise_for_status = MagicMock()

    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_resp
        res = await resolver.find_track("Starboy")

        assert res is not None
        assert res["name"] == "Starboy (feat. Daft Punk)"
        assert res["artist"] == "The Weeknd"
        assert res["uri"].startswith("spotify:search:")


@pytest.mark.asyncio
async def test_spotify_resolver_web_api_credentials():
    resolver = SpotifyResolver(client_id="test_id", client_secret="test_secret")

    token_resp = MagicMock()
    token_resp.json.return_value = {"access_token": "mock_token", "expires_in": 3600}
    token_resp.raise_for_status = MagicMock()

    search_resp = MagicMock()
    search_resp.json.return_value = {
        "tracks": {
            "items": [
                {
                    "uri": "spotify:track:4cOdK2wGLETKBW3PvgPWqT",
                    "album": {"uri": "spotify:album:2ODvWsOgouMbaA5xf0RkJe"},
                    "name": "Aruarian Dance",
                    "artists": [{"name": "Nujabes"}],
                }
            ]
        }
    }
    search_resp.raise_for_status = MagicMock()

    with (
        patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post,
        patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get,
    ):
        mock_post.return_value = token_resp
        mock_get.return_value = search_resp

        res = await resolver.find_track("Aruarian Dance")
        assert res is not None
        assert res["uri"] == "spotify:track:4cOdK2wGLETKBW3PvgPWqT"
        assert res["name"] == "Aruarian Dance"
        assert res["artist"] == "Nujabes"


@pytest.mark.asyncio
async def test_ipc_server_call_automation_no_client():
    sock_file = Path("/tmp") / f"selene_test_{uuid.uuid4().hex[:8]}.sock"
    server = SeleneIPCServer(socket_path=sock_file)
    await server.start()
    try:
        res = await server.call_automation(app="spotify", action="play_uri", args=["uri"])
        assert res["ok"] is False
        assert res["errorCode"] == "no_client"
    finally:
        await server.stop()


@pytest.mark.asyncio
async def test_ipc_server_call_automation_roundtrip():
    sock_file = Path("/tmp") / f"selene_test_{uuid.uuid4().hex[:8]}.sock"
    server = SeleneIPCServer(socket_path=sock_file)
    await server.start()

    reader, writer = await asyncio.open_unix_connection(str(sock_file))
    # Read initial state line
    _ = await reader.readline()

    try:
        async def mock_client_loop():
            line = await reader.readline()
            import json
            data = json.loads(line.decode("utf-8"))
            assert data["type"] == "automate"
            assert data["app"] == "spotify"
            req_id = data["reqId"]

            reply = {
                "cmd": "rpc_reply",
                "reqId": req_id,
                "ok": True,
                "output": "ok",
            }
            writer.write((json.dumps(reply) + "\n").encode("utf-8"))
            await writer.drain()

        client_task = asyncio.create_task(mock_client_loop())
        res = await server.call_automation(app="spotify", action="play_uri", args=["test_uri"])
        await client_task

        assert res["ok"] is True
        assert res["output"] == "ok"
    finally:
        writer.close()
        await writer.wait_closed()
        await server.stop()


def test_control_media_validation():
    assert "Rejected invalid media action" in control_media("dance")


def test_play_spotify_track_tool_registration():
    mock_memory = MagicMock()
    tools = build_jarvis_tools(memory=mock_memory)
    tool_names = [getattr(t, "__name__", "") for t in tools]
    assert "play_spotify_track" in tool_names

    spotify_tool = next(t for t in tools if getattr(t, "__name__", "") == "play_spotify_track")
    assert "Please provide a track title" in spotify_tool("")
