"""Headless track resolution for Spotify via Spotify Web API and iTunes Search API fallback."""

import base64
import logging
import time
import urllib.parse

import httpx

logger = logging.getLogger(__name__)


class SpotifyResolver:
    """Resolves arbitrary user song queries into clean track metadata and Spotify URIs."""

    def __init__(self, client_id: str = "", client_secret: str = ""):
        self.client_id = client_id.strip()
        self.client_secret = client_secret.strip()
        self._token: str | None = None
        self._token_expires_at: float = 0.0

    async def _get_spotify_token(self, client: httpx.AsyncClient) -> str | None:
        """Fetch or return cached Spotify Web API token using Client Credentials flow."""
        if not self.client_id or not self.client_secret:
            return None

        if self._token and time.monotonic() < self._token_expires_at - 60:
            return self._token

        creds = f"{self.client_id}:{self.client_secret}"
        b64_creds = base64.b64encode(creds.encode("utf-8")).decode("utf-8")
        try:
            resp = await client.post(
                "https://accounts.spotify.com/api/token",
                headers={"Authorization": f"Basic {b64_creds}"},
                data={"grant_type": "client_credentials"},
                timeout=5.0,
            )
            resp.raise_for_status()
            payload = resp.json()
            self._token = payload.get("access_token")
            expires_in = float(payload.get("expires_in", 3600))
            self._token_expires_at = time.monotonic() + expires_in
            return self._token
        except Exception as err:
            logger.warning("Failed to authenticate with Spotify Web API: %s", err)
            return None

    async def _find_via_spotify_api(
        self, client: httpx.AsyncClient, query: str
    ) -> dict[str, str] | None:
        """Query official Spotify Web API search endpoint."""
        token = await self._get_spotify_token(client)
        if not token:
            return None

        try:
            resp = await client.get(
                "https://api.spotify.com/v1/search",
                headers={"Authorization": f"Bearer {token}"},
                params={"q": query, "type": "track", "limit": 5},
                timeout=5.0,
            )
            resp.raise_for_status()
            items = resp.json().get("tracks", {}).get("items", [])
            if not items:
                return None

            top = items[0]
            artist_names = ", ".join(a["name"] for a in top.get("artists", []))
            return {
                "uri": top.get("uri", ""),
                "album_uri": top.get("album", {}).get("uri", ""),
                "name": top.get("name", "Unknown Track"),
                "artist": artist_names or "Unknown Artist",
            }
        except Exception as err:
            logger.warning("Spotify Web API search failed: %s", err)
            return None

    async def _find_via_itunes(
        self, client: httpx.AsyncClient, query: str
    ) -> dict[str, str] | None:
        """Zero-credential fallback using iTunes Search API for canonical track resolution."""
        try:
            resp = await client.get(
                "https://itunes.apple.com/search",
                params={"term": query, "entity": "song", "limit": 1},
                timeout=5.0,
            )
            resp.raise_for_status()
            results = resp.json().get("results", [])
            if not results:
                return None

            top = results[0]
            track_name = top.get("trackName", "").strip()
            artist_name = top.get("artistName", "").strip()
            if not track_name:
                return None

            search_query = f"{track_name} {artist_name}".strip()
            encoded = urllib.parse.quote(search_query)
            return {
                "uri": f"spotify:search:{encoded}",
                "album_uri": "",
                "name": track_name,
                "artist": artist_name or "Unknown Artist",
            }
        except Exception as err:
            logger.warning("iTunes search fallback failed: %s", err)
            return None

    async def find_track(self, query: str) -> dict[str, str] | None:
        """Resolve a track query into a Spotify URI and clean metadata."""
        cleaned = query.strip()
        if not cleaned:
            return None

        async with httpx.AsyncClient(timeout=6.0) as client:
            # 1. Try Spotify Web API if credentials configured
            if self.client_id and self.client_secret:
                result = await self._find_via_spotify_api(client, cleaned)
                if result:
                    return result

            # 2. Zero-credential iTunes Search fallback
            result = await self._find_via_itunes(client, cleaned)
            if result:
                return result

            # 3. Direct raw Spotify search URI fallback
            encoded = urllib.parse.quote(cleaned)
            return {
                "uri": f"spotify:search:{encoded}",
                "album_uri": "",
                "name": cleaned,
                "artist": "Various Artists",
            }
