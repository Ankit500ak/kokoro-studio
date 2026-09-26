"""
YouTube OAuth2 Client
Handles authentication, token refresh, and YouTube Data API v3 calls.
"""

import json
import logging
import os
import subprocess
import base64
import urllib.parse
from datetime import datetime, timedelta, timezone
from pathlib import Path

log = logging.getLogger(__name__)

import httpx

YOUTUBE_API_BASE = "https://www.googleapis.com/youtube/v3"
YOUTUBE_UPLOAD_URL = "https://www.googleapis.com/upload/youtube/v3/videos"
OAUTH_TOKEN_URL = "https://oauth2.googleapis.com/token"
OAUTH_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"


class YouTubeAuthError(Exception):
    pass


class YouTubeUploadError(Exception):
    pass


class YouTubeClient:
    """Low-level YouTube API client with auto token refresh."""

    def __init__(
        self,
        access_token: str,
        refresh_token: str,
        client_id: str,
        client_secret: str,
        token_expiry: datetime,
        on_token_refresh=None,
    ):
        self._access_token = access_token
        self._refresh_token_value = refresh_token
        self._client_id = client_id
        self._client_secret = client_secret
        self._token_expiry = token_expiry
        self._on_token_refresh = on_token_refresh

    @staticmethod
    def _clean_tag(tag: str) -> str:
        """Clean a tag to be YouTube-compliant."""
        import re

        tag = tag.lower().strip()
        tag = re.sub(r"[^a-z0-9\s\-]", "", tag)
        tag = re.sub(r"\s+", " ", tag).strip()
        return tag[:30]

    @staticmethod
    def _validate_shorts_video(video_path: str) -> dict:
        """Validate video for YouTube Shorts compatibility.

        Returns:
            dict with 'valid' (bool) and 'warning' (str or None)
        """
        result = {"valid": True, "warning": None}

        try:
            # Use ffprobe to get video info
            cmd = [
                "ffprobe",
                "-v",
                "error",
                "-select_streams",
                "v:0",
                "-show_entries",
                "stream=width,height,duration,r_frame_rate",
                "-show_entries",
                "format=duration",
                "-of",
                "json",
                video_path,
            ]
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
            if proc.returncode != 0:
                result["warning"] = "Could not probe video file"
                return result

            import json

            info = json.loads(proc.stdout)

            # Check duration
            duration = None
            if "streams" in info and info["streams"]:
                stream = info["streams"][0]
                if "duration" in stream:
                    duration = float(stream["duration"])

            if duration is None and "format" in info:
                duration = float(info["format"].get("duration", 0))

            if duration and duration > 120:
                result["warning"] = (
                    f"Video is {duration:.1f}s long - Shorts should be under 120s (2 min)"
                )

            # Check aspect ratio (width vs height)
            if "streams" in info and info["streams"]:
                stream = info["streams"][0]
                width = stream.get("width", 0)
                height = stream.get("height", 0)

                if width and height:
                    aspect = width / height
                    if aspect > 1:  # Landscape
                        result["warning"] = (
                            f"Video is landscape ({width}x{height}) - Shorts should be vertical (9:16)"
                        )
                    elif abs(aspect - 9 / 16) > 0.1:  # Not quite 9:16
                        result["warning"] = (
                            f"Video aspect ratio {aspect:.2f} is not 9:16 - may not display optimally as Short"
                        )

        except (subprocess.TimeoutExpired, json.JSONDecodeError, Exception) as e:
            log.debug(f"[YT] Shorts validation probe failed: {e}")
            # Don't fail upload for validation issues

        return result

    async def _ensure_token(self):
        expiry = self._token_expiry
        if expiry is None:
            await self._refresh_token()
            return
        if expiry.tzinfo is None:
            expiry = expiry.replace(tzinfo=timezone.utc)
        if datetime.now(timezone.utc) >= expiry - timedelta(minutes=5):
            await self._refresh_token()

    async def _refresh_token(self):
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                OAUTH_TOKEN_URL,
                data={
                    "client_id": self._client_id,
                    "client_secret": self._client_secret,
                    "refresh_token": self._refresh_token_value,
                    "grant_type": "refresh_token",
                },
            )
            if resp.status_code != 200:
                raise YouTubeAuthError(f"Token refresh failed: {resp.text}")
            data = resp.json()
            self._access_token = data["access_token"]
            self._token_expiry = datetime.now(timezone.utc) + timedelta(
                seconds=data.get("expires_in", 3600)
            )
            if self._on_token_refresh:
                self._on_token_refresh(self._access_token, self._token_expiry)

    async def _api_get(self, path: str, params: dict | None = None) -> dict:
        await self._ensure_token()
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                f"{YOUTUBE_API_BASE}/{path}",
                headers={"Authorization": f"Bearer {self._access_token}"},
                params=params or {},
            )
            if resp.status_code != 200:
                raise YouTubeAuthError(
                    f"API GET {path} failed ({resp.status_code}): {resp.text}"
                )
            return resp.json()

    async def _api_post(
        self, path: str, data: dict, params: dict | None = None
    ) -> dict:
        await self._ensure_token()
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{YOUTUBE_API_BASE}/{path}",
                headers={"Authorization": f"Bearer {self._access_token}"},
                json=data,
                params=params or {},
            )
            if resp.status_code not in (200, 201):
                raise YouTubeAuthError(
                    f"API POST {path} failed ({resp.status_code}): {resp.text}"
                )
            return resp.json()

    # ── Public API ──────────────────────────────────────

    async def get_channel_info(self) -> dict:
        data = await self._api_get(
            "channels", {"part": "snippet,statistics", "mine": "true"}
        )
        items = data.get("items", [])
        if not items:
            raise YouTubeAuthError("No YouTube channel found for this account")
        return items[0]

    async def list_playlists(self, max_results: int = 50) -> list[dict]:
        data = await self._api_get(
            "playlists",
            {
                "part": "snippet,contentDetails",
                "mine": "true",
                "maxResults": str(max_results),
            },
        )
        return data.get("items", [])

    async def upload_video(
        self,
        video_path: str,
        title: str,
        description: str,
        tags: list[str],
        category_id: str = "22",
        privacy_status: str = "public",
        thumbnail_path: str | None = None,
        playlist_id: str | None = None,
        schedule_time: datetime | None = None,
    ) -> dict:
        # Validate video file before upload
        if not os.path.exists(video_path):
            raise YouTubeUploadError(f"Video file not found: {video_path}")

        file_size = os.path.getsize(video_path)
        if file_size < 1000:
            raise YouTubeUploadError(
                f"Video file too small ({file_size} bytes) - likely corrupt or empty"
            )

        # YouTube Shorts limit: 287.6MB max
        max_size = 287 * 1024 * 1024  # 287MB
        if file_size > max_size:
            raise YouTubeUploadError(
                f"Video file too large ({file_size / 1024 / 1024:.1f}MB) - Shorts max is 287MB"
            )

        # Check file extension
        ext = os.path.splitext(video_path)[1].lower()
        allowed_exts = {".mp4", ".mov", ".avi", ".wmv", ".flv", ".webm", ".mkv", ".m4v"}
        if ext not in allowed_exts:
            raise YouTubeUploadError(
                f"Unsupported video format: {ext}. Allowed: {', '.join(allowed_exts)}"
            )

        # Validate video dimensions and duration for Shorts
        validation = self._validate_shorts_video(video_path)
        if not validation["valid"]:
            log.warning(f"[YT] Shorts validation warning: {validation['warning']}")
            # Don't fail upload, just log warning - YouTube will handle it

        await self._ensure_token()

        # Ensure title has #shorts for YouTube Shorts
        if "#shorts" not in title.lower():
            title = f"{title.rstrip()} #shorts"

        # Ensure tags include shorts-related tags
        tags = list(tags) if tags else []
        if "shorts" not in [t.lower() for t in tags]:
            tags.append("shorts")

        metadata = {
            "snippet": {
                "title": title[:100],
                "description": description[:5000],
                "tags": [self._clean_tag(t) for t in tags[:500] if t.strip()][:30],
                "categoryId": category_id,
                "defaultLanguage": "en",
                "defaultAudioLanguage": "en",
            },
            "status": {
                "privacyStatus": privacy_status,
                "selfDeclaredMadeForKids": False,
                "embeddable": True,
                "publicStatsViewable": True,
            },
        }

        if schedule_time and privacy_status == "private":
            metadata["status"]["publishAt"] = schedule_time.strftime(
                "%Y-%m-%dT%H:%M:%SZ"
            )

        log.info(
            f"[YT] Starting Shorts upload: {title[:50]}... ({file_size / 1024 / 1024:.1f}MB)"
        )

        async with httpx.AsyncClient(timeout=300) as client:
            init_resp = await client.post(
                f"{YOUTUBE_UPLOAD_URL}?uploadType=resumable&part=snippet,status",
                headers={
                    "Authorization": f"Bearer {self._access_token}",
                    "Content-Type": "application/json",
                    "X-Upload-Content-Type": "video/mp4",
                    "X-Upload-Content-Length": str(file_size),
                },
                json=metadata,
            )

            if init_resp.status_code not in (200, 201):
                raise YouTubeUploadError(
                    f"Upload init failed ({init_resp.status_code}): {init_resp.text}"
                )

            upload_url = init_resp.headers.get("Location")
            if not upload_url:
                raise YouTubeUploadError("No upload URL returned")

            chunk_size = 10 * 1024 * 1024  # 10MB
            offset = 0
            video_id = None

            with open(video_path, "rb") as f:
                while offset < file_size:
                    chunk = f.read(chunk_size)
                    if not chunk:
                        break
                    chunk_end = offset + len(chunk) - 1

                    resp = await client.put(
                        upload_url,
                        content=chunk,
                        headers={
                            "Content-Length": str(len(chunk)),
                            "Content-Range": f"bytes {offset}-{chunk_end}/{file_size}",
                        },
                    )

                    if resp.status_code in (200, 201):
                        result = resp.json()
                        video_id = result.get("id")
                        log.info(f"[YT] Upload complete: {video_id}")
                        break
                    elif resp.status_code == 308:
                        offset += len(chunk)
                        log.debug(f"[YT] Chunk uploaded: {offset}/{file_size}")
                    else:
                        raise YouTubeUploadError(
                            f"Upload chunk failed ({resp.status_code}): {resp.text}"
                        )

            if not video_id:
                raise YouTubeUploadError("Upload completed but no video ID returned")

            if thumbnail_path and os.path.exists(thumbnail_path):
                await self._set_thumbnail(video_id, thumbnail_path)

            if playlist_id:
                await self._add_to_playlist(video_id, playlist_id)

            return {
                "video_id": video_id,
                "url": f"https://youtube.com/watch?v={video_id}",
            }

    async def _set_thumbnail(self, video_id: str, thumbnail_path: str):
        try:
            await self._ensure_token()
            async with httpx.AsyncClient(timeout=60) as client:
                with open(thumbnail_path, "rb") as f:
                    resp = await client.post(
                        f"{YOUTUBE_API_BASE}/thumbnails/set",
                        headers={"Authorization": f"Bearer {self._access_token}"},
                        data={"videoId": video_id},
                        files={"image": ("thumbnail.jpg", f, "image/jpeg")},
                    )
                if resp.status_code in (200, 201):
                    log.info(f"[YT] Thumbnail set for {video_id}")
                elif resp.status_code in (401, 403):
                    # Needs the `youtube` / `youtube.force-ssl` scope - a
                    # youtube.upload-only token silently cannot do this.
                    log.error(
                        f"[YT] Thumbnail upload denied ({resp.status_code}): "
                        f"{resp.text[:200]} - check YOUTUBE_SCOPES includes "
                        f"'youtube' and 'youtube.force-ssl'"
                    )
                else:
                    log.error(
                        f"[YT] Thumbnail upload failed: {resp.status_code} {resp.text[:200]}"
                    )
        except Exception:
            log.exception("[YT] Thumbnail upload error")

    async def _add_to_playlist(self, video_id: str, playlist_id: str):
        try:
            await self._api_post(
                "playlistItems",
                {
                    "snippet": {
                        "playlistId": playlist_id,
                        "resourceId": {
                            "kind": "youtube#video",
                            "videoId": video_id,
                        },
                    },
                },
                {"part": "snippet"},
            )
            log.info(f"[YT] Added {video_id} to playlist {playlist_id}")
        except Exception:
            # Needs the `youtube` scope - a youtube.upload-only token cannot
            # write playlist items, and this used to vanish into a warning.
            log.exception(f"[YT] Failed to add {video_id} to playlist {playlist_id}")

    async def get_video_stats(self, video_id: str) -> dict:
        data = await self._api_get(
            "videos",
            {
                "part": "statistics,contentDetails",
                "id": video_id,
            },
        )
        items = data.get("items", [])
        if items:
            return items[0].get("statistics", {})
        return {}


def generate_auth_url(client_id: str, redirect_uri: str, scopes: list[str]) -> str:
    scope_str = " ".join(scopes)
    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": scope_str,
        "access_type": "offline",
        "prompt": "select_account consent",
    }
    query = urllib.parse.urlencode(params)
    return f"{OAUTH_AUTH_URL}?{query}"


async def exchange_code(
    code: str,
    client_id: str,
    client_secret: str,
    redirect_uri: str,
) -> dict:
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            OAUTH_TOKEN_URL,
            data={
                "code": code,
                "client_id": client_id,
                "client_secret": client_secret,
                "redirect_uri": redirect_uri,
                "grant_type": "authorization_code",
            },
        )
        if resp.status_code != 200:
            raise YouTubeAuthError(f"Code exchange failed: {resp.text}")
        return resp.json()
