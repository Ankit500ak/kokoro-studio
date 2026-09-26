"""
YouTube Upload Orchestrator
Upload queue, retry logic, and background processing.
"""

import asyncio
import json
import logging
import os
from datetime import datetime, timezone, timedelta
from dataclasses import dataclass, asdict
from pathlib import Path

from sqlalchemy.orm import Session
from ..core.database import SessionLocal
from ..core.models import YouTubeUpload
from ..core.encryption import encrypt_token, decrypt_token, decrypt_token_or_raw

from .youtube_client import YouTubeClient, YouTubeUploadError
from .metadata_generator import generate_metadata
from .thumbnail_engine import generate_thumbnail

log = logging.getLogger(__name__)

QUOTA_QUEUE_FILE = (
    Path(__file__).parent.parent.parent / "data" / "youtube_quota_queue.json"
)


@dataclass
class UploadJob:
    id: str
    render_output_id: str
    video_path: str
    thumbnail_path: str | None
    title: str
    description: str
    tags: list[str]
    privacy_status: str
    playlist_id: str | None
    scheduled_time: datetime | None
    niche: str
    status: str = "pending"
    video_id: str | None = None
    video_url: str | None = None
    error_message: str | None = None
    attempt: int = 0
    # Primary key of the YouTubeUpload row this job belongs to. Status must be
    # written back to that exact row - render_output_id alone can collide with
    # older uploads of the same render and update the wrong record.
    upload_id: str | None = None


class YouTubeUploader:
    def __init__(self):
        self.queue: list[UploadJob] = []
        self.quota_queue: list[dict] = []
        self.active_uploads = 0
        self.max_concurrent = 2
        self._running = False
        self.quota_exceeded = False
        self._load_quota_queue()

    def _load_quota_queue(self):
        try:
            if QUOTA_QUEUE_FILE.exists():
                with open(QUOTA_QUEUE_FILE, "r", encoding="utf-8") as f:
                    self.quota_queue = json.load(f)
                log.info(
                    f"[YT Upload] Loaded {len(self.quota_queue)} pending uploads from quota queue"
                )
        except Exception as e:
            log.error(f"[YT Upload] Failed to load quota queue: {e}")
            self.quota_queue = []

    def _save_quota_queue(self):
        try:
            QUOTA_QUEUE_FILE.parent.mkdir(parents=True, exist_ok=True)
            with open(QUOTA_QUEUE_FILE, "w", encoding="utf-8") as f:
                json.dump(self.quota_queue, f, indent=2, ensure_ascii=False)
        except Exception as e:
            log.error(f"[YT Upload] Failed to save quota queue: {e}")

    def _addTo_quota_queue(self, job: UploadJob):
        entry = {
            "upload_id": job.upload_id,
            "render_output_id": job.render_output_id,
            "video_path": job.video_path,
            "thumbnail_path": job.thumbnail_path,
            "title": job.title,
            "description": job.description,
            "tags": job.tags,
            "privacy_status": job.privacy_status,
            "playlist_id": job.playlist_id,
            "scheduled_time": job.scheduled_time.isoformat()
            if job.scheduled_time
            else None,
            "niche": job.niche,
            "queued_at": datetime.now(timezone.utc).isoformat(),
        }
        self.quota_queue.append(entry)
        self._save_quota_queue()
        log.info(
            f"[YT Upload] Saved to quota queue: {job.title[:50]} (total: {len(self.quota_queue)})"
        )

    async def queue_upload(
        self,
        render_output_id: str,
        video_path: str,
        niche: str = "psychology",
        topic: str = "",
        auto_metadata: bool = True,
        title_override: str | None = None,
        description_override: str | None = None,
        tags_override: list[str] | None = None,
        privacy_status: str = "public",
        playlist_id: str | None = None,
        scheduled_time: datetime | None = None,
        upload_id: str | None = None,
    ) -> UploadJob:
        import uuid

        job_id = uuid.uuid4().hex[:12]

        if auto_metadata and not title_override:
            metadata = await generate_metadata(topic, niche, title_override)
            title = metadata.title
            description = metadata.description
            tags = metadata.tags
        else:
            title = title_override or f"{topic} - {niche}"
            description = description_override or ""
            tags = tags_override or []

        # Generate thumbnail
        thumb_path = None
        if os.path.exists(video_path):
            thumb_dir = os.path.dirname(video_path)
            thumb_path = os.path.join(thumb_dir, f"{job_id}_yt_thumb.jpg")
            result = generate_thumbnail(video_path, title, niche, thumb_path)
            if not result:
                thumb_path = None

        job = UploadJob(
            id=job_id,
            render_output_id=render_output_id,
            video_path=video_path,
            thumbnail_path=thumb_path,
            title=title,
            description=description,
            tags=tags,
            privacy_status=privacy_status,
            playlist_id=playlist_id,
            scheduled_time=scheduled_time,
            niche=niche,
            upload_id=upload_id,
        )

        self.queue.append(job)
        log.info(f"[YT Upload] Queued: {title[:50]}... (queue size: {len(self.queue)})")
        return job

    async def start_processing(self):
        if self._running:
            return
        self._running = True
        log.info("[YT Upload] Queue processor started")
        last_quota_reset = datetime.now(timezone.utc)
        while self._running:
            now = datetime.now(timezone.utc)
            if self.quota_exceeded:
                hours_since = (now - last_quota_reset).total_seconds() / 3600
                if hours_since >= 23:
                    self.quota_exceeded = False
                    last_quota_reset = now
                    log.info("[YT Upload] Quota reset — resuming uploads")
                    self._reload_quota_queue()
                else:
                    await asyncio.sleep(60)
                    continue
            if self.active_uploads < self.max_concurrent and self.queue:
                job = self.queue.pop(0)
                asyncio.create_task(self._process_job(job))
            await asyncio.sleep(3)

    def _reload_quota_queue(self):
        if not self.quota_queue:
            return
        log.info(
            f"[YT Upload] Reloading {len(self.quota_queue)} pending uploads from quota queue"
        )
        for entry in self.quota_queue:
            import uuid

            video_path = entry["video_path"]
            if not video_path or not os.path.exists(video_path):
                log.warning(
                    f"[YT Upload] Skipping queued upload, video missing: "
                    f"{entry.get('title', '?')[:50]}"
                )
                continue

            job = UploadJob(
                id=uuid.uuid4().hex[:12],
                render_output_id=entry["render_output_id"],
                upload_id=entry.get("upload_id"),
                video_path=entry["video_path"],
                thumbnail_path=entry.get("thumbnail_path"),
                title=entry["title"],
                description=entry["description"],
                tags=entry["tags"],
                privacy_status=entry["privacy_status"],
                playlist_id=entry.get("playlist_id"),
                scheduled_time=datetime.fromisoformat(entry["scheduled_time"])
                if entry.get("scheduled_time")
                else None,
                niche=entry["niche"],
            )
            self.queue.append(job)
        self.quota_queue.clear()
        self._save_quota_queue()
        log.info(f"[YT Upload] Reloaded {len(self.queue)} jobs into upload queue")

    def _reap_stale_quota_entries(self, max_age_hours: int = 24) -> None:
        """Drop quota-queue entries that can no longer be retried."""
        if not self.quota_queue:
            return
        cutoff = datetime.now(timezone.utc) - timedelta(hours=max_age_hours)
        fresh = []
        dropped = 0
        for entry in self.quota_queue:
            try:
                queued_at = datetime.fromisoformat(str(entry.get("queued_at", "")))
                if queued_at.tzinfo is None:
                    queued_at = queued_at.replace(tzinfo=timezone.utc)
            except ValueError:
                queued_at = None
            if queued_at is None or queued_at < cutoff:
                dropped += 1
            else:
                fresh.append(entry)
        if dropped:
            self.quota_queue = fresh
            self._save_quota_queue()
            log.warning(
                f"[YT Upload] Dropped {dropped} stale quota-queue entries "
                f"older than {max_age_hours}h"
            )

    def startup_maintenance(self) -> None:
        """Reap state that cannot be valid after a restart.

        The upload queue only lives in memory, so any YouTubeUpload row still
        marked queued/uploading when the process boots is an orphan with no
        worker behind it - it would otherwise stay "queued" forever.
        """
        self._reap_stale_quota_entries()
        try:
            db = SessionLocal()
            try:
                rows = (
                    db.query(YouTubeUpload)
                    .filter(
                        YouTubeUpload.status.in_(
                            ["queued", "pending", "uploading", "retrying"]
                        )
                    )
                    .all()
                )
                for row in rows:
                    row.status = "failed"
                    row.error_message = "Upload was lost when the backend restarted"
                if rows:
                    db.commit()
                    log.warning(
                        f"[YT Upload] Reaped {len(rows)} orphaned upload rows"
                    )
            finally:
                db.close()
        except Exception as e:
            log.error(f"[YT Upload] Startup maintenance failed: {e}")

    def stop_processing(self):
        self._running = False

    def _cleanup_temp_files(self, job: UploadJob):
        """Clean up temporary files from direct uploads."""
        try:
            if job.video_path and os.path.exists(job.video_path):
                os.remove(job.video_path)
                log.info(f"[YT Upload] Cleaned up temp video: {job.video_path}")
            if job.thumbnail_path and os.path.exists(job.thumbnail_path):
                os.remove(job.thumbnail_path)
                log.info(f"[YT Upload] Cleaned up temp thumbnail: {job.thumbnail_path}")
        except Exception as e:
            log.warning(f"[YT Upload] Failed to cleanup temp files: {e}")

    async def _process_job(self, job: UploadJob):
        self.active_uploads += 1
        job.status = "uploading"
        job.attempt += 1
        is_direct_upload = "direct_" in job.render_output_id

        try:
            credential = await self._get_credential()
            if not credential:
                job.status = "failed"
                job.error_message = "No YouTube credentials configured"
                return

            def on_refresh(token, expiry):
                asyncio.create_task(
                    self._save_refreshed_token(credential, token, expiry)
                )

            client = YouTubeClient(
                access_token=credential["access_token"],
                refresh_token=credential["refresh_token"],
                client_id=credential["client_id"],
                client_secret=credential["client_secret"],
                token_expiry=credential["token_expiry"],
                on_token_refresh=on_refresh,
            )

            result = await client.upload_video(
                video_path=job.video_path,
                title=job.title,
                description=job.description,
                tags=job.tags,
                privacy_status=job.privacy_status,
                thumbnail_path=job.thumbnail_path,
                playlist_id=job.playlist_id,
                schedule_time=job.scheduled_time,
            )

            job.video_id = result["video_id"]
            job.video_url = result["url"]
            job.status = "uploaded"
            log.info(f"[YT Upload] Success: {job.title[:50]} -> {job.video_url}")

        except YouTubeUploadError as e:
            job.error_message = str(e)
            error_str = str(e).lower()
            no_retry_errors = [
                "uploadlimitexceeded",
                "quotaexceeded",
                "rateLimitExceeded",
                "forbidden",
                "exceeded",
            ]
            is_quota_error = any(err in error_str for err in no_retry_errors)
            # Permanent configuration failures - retrying can never succeed.
            is_permanent_error = "re-authorize" in error_str

            if is_quota_error:
                self.quota_exceeded = True
                job.status = "failed"
                job.error_message = (
                    "YouTube upload quota exceeded. Will retry after quota resets."
                )
                self._addTo_quota_queue(job)
                log.warning(
                    f"[YT Upload] Quota hit — saved to retry queue: {job.title[:50]}"
                )
            elif job.attempt < 3 and not is_permanent_error:
                job.status = "retrying"
                self.queue.append(job)
                log.warning(f"[YT Upload] Retry {job.attempt}/3: {job.title[:50]}")
            else:
                job.status = "failed"
                log.error(f"[YT Upload] Failed after {job.attempt} attempts: {e}")

        except Exception as e:
            job.status = "failed"
            job.error_message = str(e)
            log.exception(f"[YT Upload] Unexpected error: {e}")

        finally:
            self.active_uploads -= 1
            # Sync status to YouTubeUpload DB record
            await self._sync_upload_status(job)
            # Cleanup temp files for direct uploads (not for render outputs which are managed elsewhere)
            if is_direct_upload and job.status in ("uploaded", "failed"):
                self._cleanup_temp_files(job)

    async def _sync_upload_status(self, job: UploadJob):
        """Sync the UploadJob status to the corresponding YouTubeUpload DB record."""
        try:
            db = SessionLocal()
            try:
                query = db.query(YouTubeUpload)
                if job.upload_id:
                    upload_record = query.filter(
                        YouTubeUpload.id == job.upload_id
                    ).first()
                else:
                    # Fallback: newest record for this render output. render_output_id
                    # is not unique, so an unfiltered .first() can hit an old row.
                    upload_record = (
                        query.filter(
                            YouTubeUpload.render_output_id == job.render_output_id
                        )
                        .order_by(YouTubeUpload.created_at.desc())
                        .first()
                    )
                if not upload_record:
                    log.warning(
                        f"[YT Upload] No YouTubeUpload record found for upload_id="
                        f"{job.upload_id} render_output_id={job.render_output_id}"
                    )
                    return

                upload_record.status = job.status
                upload_record.video_id = job.video_id
                upload_record.video_url = job.video_url
                if job.error_message:
                    upload_record.error_message = job.error_message
                if job.status == "uploaded":
                    upload_record.uploaded_at = datetime.utcnow()
                db.commit()
                log.info(
                    f"[YT Upload] Synced status '{job.status}' to YouTubeUpload record {upload_record.id}"
                )
            except Exception as e:
                db.rollback()
                log.error(f"[YT Upload] Failed to sync status to DB: {e}")
        finally:
            db.close()

    async def _get_credential(self) -> dict | None:
        try:
            from ..core.database import SessionLocal
            from ..core.models import YouTubeCredential

            db = SessionLocal()
            try:
                cred = (
                    db.query(YouTubeCredential)
                    .filter(YouTubeCredential.is_active == True)
                    .first()
                )
                if not cred:
                    return None
                try:
                    access_token = decrypt_token(cred.access_token)
                    refresh_token = decrypt_token(cred.refresh_token)
                except Exception as e:
                    log.error(
                        "[YT Upload] Stored YouTube tokens cannot be decrypted "
                        "(ENCRYPTION_KEY missing or changed): %s: %s",
                        type(e).__name__,
                        e or repr(e),
                    )
                    raise YouTubeUploadError(
                        "Stored YouTube credentials are unreadable. "
                        "Re-authorize at /api/youtube/auth"
                    )
                return {
                    "access_token": access_token,
                    "refresh_token": refresh_token,
                    # client_id / client_secret are persisted in plaintext by the
                    # OAuth callback - strict decryption always failed on them.
                    "client_id": decrypt_token_or_raw(cred.client_id),
                    "client_secret": decrypt_token_or_raw(cred.client_secret),
                    "token_expiry": cred.token_expiry,
                    "id": cred.id,
                }
            finally:
                db.close()
        except YouTubeUploadError:
            raise
        except Exception as e:
            log.error(f"[YT Upload] Failed to get credential: {e}")
            return None

    async def _save_refreshed_token(
        self, credential: dict, new_token: str, new_expiry: datetime
    ):
        try:
            from ..core.database import SessionLocal
            from ..core.models import YouTubeCredential

            db = SessionLocal()
            try:
                cred = (
                    db.query(YouTubeCredential)
                    .filter(YouTubeCredential.id == credential["id"])
                    .first()
                )
                if cred:
                    cred.access_token = encrypt_token(new_token)
                    cred.token_expiry = new_expiry
                    db.commit()
            finally:
                db.close()
        except Exception as e:
            log.error(f"[YT Upload] Failed to save refreshed token: {e}")


uploader = YouTubeUploader()
