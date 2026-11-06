"""
YouTube Auto-Upload Service
Uploads finished renders to YouTube automatically when a render job
completes - no manual POST /api/youtube/upload needed.

Design rules:
- Opt-in only: does nothing unless settings.AUTO_UPLOAD_YOUTUBE is on.
- Safe defaults: uploads start with settings.UPLOAD_PRIVACY_STATUS
  ("private" unless changed), so a human reviews before anything is public.
- Never breaks the caller: every public entry point reports an outcome
  dict instead of raising, and the render pipeline dispatches this from a
  fire-and-forget thread, so an upload problem can never fail a render.

The actual transfer reuses YouTubeClient.upload_video, which already
speaks the YouTube resumable-upload protocol (initiate -> chunked PUTs
with Content-Range, 10MB chunks). This service adds the auto-upload
policy on top: metadata building, credential gating, retry with
exponential backoff on transient errors, YouTubeUpload bookkeeping and
Telegram notification. (google-api-python-client / MediaFileUpload is
deliberately not used - it is not a project dependency, and the client
already implements the same resumable protocol over httpx.)
"""

import asyncio
import json
import logging
import os
import threading
import uuid
from datetime import datetime

import httpx

from ..core.config import settings
from ..core.database import SessionLocal
from ..core.models import YouTubeUpload
from .youtube_client import YouTubeClient, YouTubeUploadError
from .youtube_uploader import uploader

log = logging.getLogger(__name__)

DESCRIPTION_FOOTER = (
    "Created with Kokoro Studio - AI narration by Kokoro TTS, "
    "script by Story Forge."
)
MAX_TITLE_LENGTH = 100  # YouTube rejects longer titles
MAX_DESCRIPTION_LENGTH = 5000  # YouTube description limit
MAX_UPLOAD_ATTEMPTS = 3
_INITIAL_BACKOFF_SECONDS = 2.0

# Substrings (matched case-insensitively) that mark an upload error as
# worth retrying. Quota and permission errors are deliberately absent:
# retrying those cannot succeed and would burn quota.
_TRANSIENT_MARKERS = (
    "500",
    "502",
    "503",
    "504",
    "408",
    "429",
    "ratelimitexceeded",
    "userratelimitexceeded",
    "timeout",
    "timed out",
    "connection",
    "temporarily",
    "internal error",
)


class AutoUploadCredentialsError(YouTubeUploadError):
    """YouTube credentials are missing, unreadable, or need re-auth."""


# ── Metadata ────────────────────────────────────────────────


def parse_config_tags(raw: str | None) -> list[str]:
    """Parse the comma-separated UPLOAD_TAGS setting into clean tags."""
    if not raw:
        return []
    return [part.strip() for part in str(raw).split(",") if part.strip()]


def build_metadata(
    title: str,
    description: str = "",
    tags: list[str] | None = None,
    *,
    privacy_status: str | None = None,
    category_id: str | None = None,
) -> dict:
    """Build the YouTube metadata dict for an auto-upload. Pure function.

    - Title is whitespace-collapsed and truncated to YouTube's 100 chars.
    - Description is the given body plus a fixed Kokoro Studio footer,
      capped at YouTube's 5000 chars.
    - Tags are the story/render tags merged with settings.UPLOAD_TAGS,
      de-duplicated case-insensitively, order preserved.
    - privacyStatus / categoryId fall back to the UPLOAD_* settings.
    """
    clean_title = " ".join(str(title or "").split()) or "Untitled video"
    if len(clean_title) > MAX_TITLE_LENGTH:
        clean_title = clean_title[: MAX_TITLE_LENGTH - 3].rstrip() + "..."

    body = (description or "").strip()
    full_description = (
        f"{body}\n\n---\n{DESCRIPTION_FOOTER}" if body else DESCRIPTION_FOOTER
    )

    merged_tags: list[str] = []
    seen: set[str] = set()
    for raw_tag in [*(tags or []), *parse_config_tags(settings.UPLOAD_TAGS)]:
        tag = str(raw_tag).strip()
        if tag and tag.lower() not in seen:
            seen.add(tag.lower())
            merged_tags.append(tag)

    return {
        "title": clean_title,
        "description": full_description[:MAX_DESCRIPTION_LENGTH],
        "tags": merged_tags,
        "categoryId": str(category_id or settings.UPLOAD_CATEGORY_ID),
        "privacyStatus": privacy_status or settings.UPLOAD_PRIVACY_STATUS,
    }


# ── Credentials ─────────────────────────────────────────────


async def _load_active_credential() -> dict | None:
    """Return the active YouTube credential dict, or None if not connected.

    Raises AutoUploadCredentialsError when stored tokens exist but cannot
    be used (e.g. ENCRYPTION_KEY changed) - the fix is re-authorizing.
    """
    try:
        return await uploader._get_credential()
    except YouTubeUploadError as e:
        raise AutoUploadCredentialsError(str(e)) from e


async def _require_credential() -> dict:
    credential = await _load_active_credential()
    if not credential:
        raise AutoUploadCredentialsError(
            "No YouTube credentials configured - connect YouTube once "
            "at /api/youtube/auth before enabling auto-upload"
        )
    return credential


# ── Bookkeeping (YouTubeUpload rows, same shape as the manual flow) ──


def _already_uploaded(render_output_id: str) -> bool:
    db = SessionLocal()
    try:
        row = (
            db.query(YouTubeUpload)
            .filter(
                YouTubeUpload.render_output_id == render_output_id,
                YouTubeUpload.video_id.isnot(None),
            )
            .first()
        )
        return row is not None
    finally:
        db.close()


def _create_upload_record(
    render_output_id: str, metadata: dict, thumbnail_path: str | None
) -> str:
    db = SessionLocal()
    try:
        record = YouTubeUpload(
            id=str(uuid.uuid4()),
            render_output_id=render_output_id,
            title=metadata["title"],
            description=metadata["description"],
            tags=json.dumps(metadata["tags"]),
            thumbnail_path=thumbnail_path,
            privacy_status=metadata["privacyStatus"],
            status="uploading",
        )
        db.add(record)
        db.commit()
        return record.id
    finally:
        db.close()


def _update_upload_record(
    record_id: str,
    *,
    status: str,
    video_id: str | None = None,
    video_url: str | None = None,
    error_message: str | None = None,
) -> None:
    db = SessionLocal()
    try:
        record = db.query(YouTubeUpload).filter(YouTubeUpload.id == record_id).first()
        if not record:
            return
        record.status = status
        if video_id:
            record.video_id = video_id
        if video_url:
            record.video_url = video_url
        if error_message:
            record.error_message = error_message
        if status == "uploaded":
            record.uploaded_at = datetime.utcnow()
        db.commit()
    finally:
        db.close()


# ── Notification ────────────────────────────────────────────


async def _notify_telegram(text: str) -> None:
    """Best-effort Telegram message via the Bot API. Never raises."""
    if not settings.UPLOAD_NOTIFY_TELEGRAM:
        return
    token = settings.TELEGRAM_BOT_TOKEN
    chat_id = settings.TELEGRAM_CHAT_ID
    if not token or not chat_id:
        return
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            await client.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json={"chat_id": chat_id, "text": text},
            )
    except Exception as e:
        log.warning(f"[YT Auto] Telegram notification failed: {e}")


# ── Upload with retry ───────────────────────────────────────


def _is_transient_error(error: Exception) -> bool:
    if isinstance(error, httpx.TransportError):
        return True
    message = str(error).lower()
    return any(marker in message for marker in _TRANSIENT_MARKERS)


async def _upload_with_retry(
    client: YouTubeClient,
    video_path: str,
    metadata: dict,
    thumbnail_path: str | None,
) -> dict:
    """Upload via the resumable client, retrying transient failures only."""
    backoff = _INITIAL_BACKOFF_SECONDS
    last_error: Exception | None = None
    for attempt in range(1, MAX_UPLOAD_ATTEMPTS + 1):
        try:
            return await client.upload_video(
                video_path=video_path,
                title=metadata["title"],
                description=metadata["description"],
                tags=metadata["tags"],
                category_id=metadata["categoryId"],
                privacy_status=metadata["privacyStatus"],
                thumbnail_path=thumbnail_path,
            )
        except Exception as e:
            last_error = e
            if attempt >= MAX_UPLOAD_ATTEMPTS or not _is_transient_error(e):
                raise
            log.warning(
                f"[YT Auto] Transient upload error (attempt {attempt}/"
                f"{MAX_UPLOAD_ATTEMPTS}), retrying in {backoff:.0f}s: {e}"
            )
            await asyncio.sleep(backoff)
            backoff *= 2
    raise last_error  # pragma: no cover - loop always returns or raises


# ── Entry points ────────────────────────────────────────────


async def auto_upload_render(
    render_output_id: str,
    video_path: str,
    *,
    title: str = "",
    description: str = "",
    tags: list[str] | None = None,
    thumbnail_path: str | None = None,
) -> dict:
    """Auto-upload one finished render. Never raises.

    Returns an outcome dict: {"status": "skipped" | "uploaded" | "failed",
    ...}. "skipped" covers every clean no-op: feature off, file missing,
    already uploaded, or YouTube not connected.
    """
    if not settings.AUTO_UPLOAD_YOUTUBE:
        return {"status": "skipped", "reason": "AUTO_UPLOAD_YOUTUBE is off"}

    if not video_path or not os.path.exists(video_path):
        return {
            "status": "skipped",
            "reason": f"video file not found: {video_path}",
        }

    if _already_uploaded(render_output_id):
        log.info(f"[YT Auto] Render {render_output_id} already uploaded, skipping")
        return {"status": "skipped", "reason": "render already uploaded"}

    try:
        credential = await _require_credential()
    except AutoUploadCredentialsError as e:
        log.warning(f"[YT Auto] Skipping auto-upload: {e}")
        return {"status": "skipped", "reason": str(e)}

    metadata = build_metadata(title, description, tags)
    record_id = _create_upload_record(render_output_id, metadata, thumbnail_path)

    def on_refresh(token, expiry):
        asyncio.create_task(uploader._save_refreshed_token(credential, token, expiry))

    client = YouTubeClient(
        access_token=credential["access_token"],
        refresh_token=credential["refresh_token"],
        client_id=credential["client_id"],
        client_secret=credential["client_secret"],
        token_expiry=credential["token_expiry"],
        on_token_refresh=on_refresh,
    )

    try:
        result = await _upload_with_retry(client, video_path, metadata, thumbnail_path)
    except Exception as e:
        _update_upload_record(record_id, status="failed", error_message=str(e))
        log.error(f"[YT Auto] Upload failed for render {render_output_id}: {e}")
        await _notify_telegram(
            f"❌ YouTube auto-upload failed: {metadata['title']}\n"
            f"{type(e).__name__}: {e}"
        )
        return {"status": "failed", "error": str(e), "upload_id": record_id}

    _update_upload_record(
        record_id,
        status="uploaded",
        video_id=result["video_id"],
        video_url=result["url"],
    )
    log.info(f"[YT Auto] Uploaded render {render_output_id} -> {result['url']}")
    await _notify_telegram(
        f"✅ Auto-uploaded to YouTube: {metadata['title']}\n{result['url']}"
    )
    return {
        "status": "uploaded",
        "video_id": result["video_id"],
        "video_url": result["url"],
        "upload_id": record_id,
    }


def dispatch_auto_upload(
    render_output_id: str,
    video_path: str,
    *,
    title: str = "",
    description: str = "",
    tags: list[str] | None = None,
    thumbnail_path: str | None = None,
) -> bool:
    """Sync fire-and-forget entry point for the (sync) render pipeline.

    Returns False without doing anything when auto-upload is disabled, so
    the caller pays ~zero cost in the default configuration. The upload
    runs on a daemon thread; its outcome is logged, recorded on the
    YouTubeUpload row, and (optionally) sent to Telegram - it can never
    block or fail the render that triggered it.
    """
    if not settings.AUTO_UPLOAD_YOUTUBE:
        return False

    def _run() -> None:
        try:
            outcome = asyncio.run(
                auto_upload_render(
                    render_output_id,
                    video_path,
                    title=title,
                    description=description,
                    tags=tags,
                    thumbnail_path=thumbnail_path,
                )
            )
            log.info(f"[YT Auto] Render {render_output_id}: {outcome}")
        except Exception:
            log.exception(
                f"[YT Auto] Auto-upload crashed for render {render_output_id}"
            )

    threading.Thread(target=_run, daemon=True, name="yt-auto-upload").start()
    return True
