"""
YouTube Upload API
Endpoints for auth, upload, metadata, thumbnails, and analytics.
"""

import json
import logging
import html
from datetime import datetime, timezone, timedelta
from app.core.encryption import encrypt_token, decrypt_token
from fastapi import (
    APIRouter,
    HTTPException,
    BackgroundTasks,
    Depends,
    UploadFile,
    File,
    Form,
)
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session
import os
import shutil
import uuid

from ..core.database import get_db
from ..core.models import YouTubeCredential, YouTubeUpload, RenderOutput, RenderJob
from ..core.config import settings
from ..schemas.youtube import (
    YouTubeUploadRequest,
    YouTubeUploadResponse,
    YouTubeUploadListResponse,
    MetadataPreviewRequest,
    MetadataPreviewResponse,
    YouTubeAuthResponse,
    YouTubeStatusResponse,
    DirectUploadRequest,
)
from ..services.youtube_client import (
    YouTubeClient,
    generate_auth_url,
    exchange_code,
    YouTubeAuthError,
)
from ..services.youtube_uploader import uploader
from ..services.metadata_generator import generate_metadata
from ..services.thumbnail_engine import generate_thumbnail

log = logging.getLogger(__name__)

router = APIRouter(prefix="/youtube", tags=["youtube"])


# ─────────────────────────────────────────────────────
# Authentication
# ─────────────────────────────────────────────────────


@router.get("/auth")
async def start_auth():
    if not settings.YOUTUBE_CLIENT_ID:
        return {
            "auth_url": None,
            "message": "YouTube not configured. Set YOUTUBE_CLIENT_ID in .env to enable YouTube integration.",
        }
    auth_url = generate_auth_url(
        client_id=settings.YOUTUBE_CLIENT_ID,
        redirect_uri=settings.YOUTUBE_REDIRECT_URI,
        scopes=settings.YOUTUBE_SCOPES.split(),
    )
    return {
        "auth_url": auth_url,
        "message": "Visit this URL to authorize YouTube access",
    }


@router.get("/callback")
async def auth_callback(code: str = "", state: str = "", db: Session = Depends(get_db)):
    if not code:
        raise HTTPException(status_code=400, detail="Authorization code not provided")

    try:
        token_data = await exchange_code(
            code=code,
            client_id=settings.YOUTUBE_CLIENT_ID,
            client_secret=settings.YOUTUBE_CLIENT_SECRET,
            redirect_uri=settings.YOUTUBE_REDIRECT_URI,
        )
    except YouTubeAuthError as e:
        raise HTTPException(status_code=400, detail=f"Token exchange failed: {e}")

    expiry = datetime.now(timezone.utc) + timedelta(
        seconds=token_data.get("expires_in", 3600)
    )

    client = YouTubeClient(
        access_token=token_data["access_token"],
        refresh_token=token_data["refresh_token"],
        client_id=settings.YOUTUBE_CLIENT_ID,
        client_secret=settings.YOUTUBE_CLIENT_SECRET,
        token_expiry=expiry,
    )

    channel_info = {}
    try:
        channel_info = await client.get_channel_info()
    except Exception as e:
        # channel_title/channel_id stay NULL when this fails, so surface it.
        log.error(
            f"[YT] Failed to get channel info during callback: {e} "
            "- channel_title/channel_id will be empty. Requires the "
            "'youtube' scope (channels?mine=true)."
        )

    # Look the row up by primary key, not by is_active: /disconnect only flips
    # is_active to False, so a reconnect would otherwise try to INSERT a second
    # 'default' row and die on the UNIQUE constraint.
    existing = (
        db.query(YouTubeCredential)
        .filter(YouTubeCredential.id == "default")
        .first()
    ) or db.query(YouTubeCredential).order_by(YouTubeCredential.id).first()

    # Google only returns refresh_token on first consent (or with prompt=consent).
    # Reuse the stored one when this response omits it instead of raising KeyError.
    fresh_refresh = token_data.get("refresh_token")
    stored_refresh = existing.refresh_token if existing else None
    refresh_token = fresh_refresh or stored_refresh
    if not refresh_token:
        raise HTTPException(
            status_code=400,
            detail=(
                "Google did not return a refresh token. Revoke this app at "
                "https://myaccount.google.com/permissions, then authorize again."
            ),
        )
    if not fresh_refresh:
        # We are about to commit to the already-stored token, so make sure it is
        # still readable under the current ENCRYPTION_KEY before saying "connected".
        try:
            decrypt_token(stored_refresh)
        except Exception:
            raise HTTPException(
                status_code=400,
                detail=(
                    "Google returned no refresh token and the stored one is "
                    "unreadable. Revoke this app at "
                    "https://myaccount.google.com/permissions, then authorize "
                    "again with a fresh consent."
                ),
            )

    # A fresh token from Google is plaintext and must be encrypted; a reused
    # stored value is already ciphertext and must be written back verbatim.
    refresh_token_to_store = (
        encrypt_token(fresh_refresh) if fresh_refresh else stored_refresh
    )

    if existing:
        existing.access_token = encrypt_token(token_data["access_token"])
        existing.refresh_token = refresh_token_to_store
        existing.token_expiry = expiry
        existing.client_id = settings.YOUTUBE_CLIENT_ID
        existing.client_secret = settings.YOUTUBE_CLIENT_SECRET
        existing.scopes = settings.YOUTUBE_SCOPES
        existing.channel_id = channel_info.get("id")
        existing.channel_title = channel_info.get("snippet", {}).get("title")
        existing.is_active = True
    else:
        cred = YouTubeCredential(
            id="default",
            access_token=encrypt_token(token_data["access_token"]),
            refresh_token=refresh_token_to_store,
            token_expiry=expiry,
            client_id=settings.YOUTUBE_CLIENT_ID,
            client_secret=settings.YOUTUBE_CLIENT_SECRET,
            scopes=settings.YOUTUBE_SCOPES,
            channel_id=channel_info.get("id"),
            channel_title=channel_info.get("snippet", {}).get("title"),
        )
        db.add(cred)
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise

    channel_name = html.escape(
        channel_info.get("snippet", {}).get("title") or "your channel"
    )
    # This endpoint is reached via the OAuth redirect in the popup window, so
    # render a page the user can read and close instead of raw JSON.
    return HTMLResponse(
        f"""<!doctype html>
<html><head><meta charset="utf-8"><title>YouTube connected</title>
<style>
body{{font-family:system-ui,sans-serif;background:#0f1115;color:#e6e8eb;
display:flex;align-items:center;justify-content:center;height:100vh;margin:0}}
.card{{background:#171a21;border:1px solid #2a2f3a;border-radius:12px;
padding:32px;max-width:360px;text-align:center}}
h1{{font-size:18px;margin:0 0 8px;color:#4ade80}}
p{{font-size:13px;margin:0 0 16px;color:#9aa3b2}}
button{{background:#dc2626;color:#fff;border:0;border-radius:8px;
padding:9px 18px;font-size:13px;cursor:pointer}}
</style></head>
<body><div class="card">
<h1>Connected</h1>
<p>Kokoro Studio is now linked to <b>{channel_name}</b>.<br>
You can close this window and return to the app.</p>
<button onclick="window.close()">Close window</button>
</div>
<script>setTimeout(function(){{window.close()}}, 15000)</script>
</body></html>"""
    )


def _utc_naive(dt: datetime | None) -> datetime | None:
    """Normalize a stored timestamp to naive UTC so it can be compared safely."""
    if dt is None:
        return None
    if dt.tzinfo is not None:
        return dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt


@router.get("/status", response_model=YouTubeStatusResponse)
async def auth_status(db: Session = Depends(get_db)):
    cred = (
        db.query(YouTubeCredential).filter(YouTubeCredential.is_active == True).first()
    )
    if not cred:
        return YouTubeStatusResponse(connected=False)

    expiry = _utc_naive(cred.token_expiry)
    if expiry and expiry < datetime.utcnow():
        # The access token lapses every hour but the refresh token stays valid.
        # Without refreshing here, every caller (Telegram bot, UI) sees
        # connected=false forever and stops attempting uploads - a deadlock,
        # because the only code that refreshed lived inside an upload.
        try:
            client = YouTubeClient(
                access_token=decrypt_token(cred.access_token),
                refresh_token=decrypt_token(cred.refresh_token),
                client_id=cred.client_id,
                client_secret=cred.client_secret,
                token_expiry=cred.token_expiry,
            )
            await client._ensure_token()
            new_expiry = _utc_naive(client._token_expiry)
            if client._access_token and new_expiry:
                cred.access_token = encrypt_token(client._access_token)
                cred.token_expiry = client._token_expiry
                db.commit()
                expiry = new_expiry
                log.info("[YT] Refreshed expired access token during /status")
        except Exception as e:
            db.rollback()
            # Fernet raises InvalidToken() with no args, so str(e) is often empty.
            log.warning(
                "[YT] Token refresh during /status failed: %s: %s",
                type(e).__name__,
                e or repr(e),
            )
            return YouTubeStatusResponse(connected=False)

    if not expiry or expiry < datetime.utcnow():
        return YouTubeStatusResponse(connected=False)
    return YouTubeStatusResponse(
        connected=True,
        channel_title=cred.channel_title,
        channel_id=cred.channel_id,
        expires_at=cred.token_expiry.isoformat() if cred.token_expiry else None,
    )


@router.post("/disconnect")
async def disconnect(db: Session = Depends(get_db)):
    cred = (
        db.query(YouTubeCredential).filter(YouTubeCredential.is_active == True).first()
    )
    if cred:
        cred.is_active = False
        try:
            db.commit()
        except Exception:
            db.rollback()
            raise
    return {"message": "Disconnected from YouTube"}


# ─────────────────────────────────────────────────────
# Metadata Generation
# ─────────────────────────────────────────────────────


@router.post("/metadata/preview", response_model=MetadataPreviewResponse)
async def preview_metadata(req: MetadataPreviewRequest):
    metadata = await generate_metadata(
        topic=req.topic,
        niche=req.niche,
        title_override=req.title_override,
    )
    return MetadataPreviewResponse(
        title=metadata.title,
        description=metadata.description,
        tags=metadata.tags,
        hashtags=metadata.hashtags,
        title_options=metadata.title_options,
        category_id=metadata.category_id,
    )


# ─────────────────────────────────────────────────────
# Thumbnail
# ─────────────────────────────────────────────────────


@router.post("/thumbnail/generate")
async def generate_thumbnail_endpoint(
    render_output_id: str,
    title: str,
    niche: str = "psychology",
    db: Session = Depends(get_db),
):
    output = db.query(RenderOutput).filter(RenderOutput.id == render_output_id).first()
    if not output:
        raise HTTPException(status_code=404, detail="Render output not found")

    job = db.query(RenderJob).filter(RenderJob.id == output.render_job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Render job not found")

    video_filename = output.video_filename
    video_path = str(settings.RENDER_DIR / video_filename) if video_filename else None
    if video_path and not os.path.exists(video_path) and video_filename:
        subdir_path = str(settings.RENDER_DIR / job.id / video_filename)
        if os.path.exists(subdir_path):
            video_path = subdir_path

    if not video_path or not os.path.exists(video_path):
        raise HTTPException(status_code=404, detail="Video file not found")

    thumb_dir = settings.RENDER_DIR / job.id
    thumb_dir.mkdir(parents=True, exist_ok=True)
    thumb_path = str(thumb_dir / f"{job.id}_yt_thumb.jpg")

    result = generate_thumbnail(str(video_path), title, niche, thumb_path)
    if not result:
        raise HTTPException(status_code=500, detail="Thumbnail generation failed")

    return {"thumbnail_path": thumb_path, "filename": os.path.basename(thumb_path)}


# ─────────────────────────────────────────────────────
# Upload
# ─────────────────────────────────────────────────────


@router.post("/upload", response_model=YouTubeUploadResponse)
async def upload_video(
    req: YouTubeUploadRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    cred = (
        db.query(YouTubeCredential).filter(YouTubeCredential.is_active == True).first()
    )
    if not cred:
        raise HTTPException(
            status_code=400,
            detail="YouTube not connected. Visit /api/youtube/auth first.",
        )

    if uploader.quota_exceeded:
        pending = len(uploader.quota_queue)
        raise HTTPException(
            status_code=429,
            detail=f"YouTube upload quota exceeded. {pending} videos pending retry. Quota resets at midnight Pacific Time.",
        )

    output = (
        db.query(RenderOutput).filter(RenderOutput.id == req.render_output_id).first()
    )
    if not output:
        raise HTTPException(status_code=404, detail="Render output not found")

    job = db.query(RenderJob).filter(RenderJob.id == output.render_job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Render job not found")

    video_filename = output.video_filename
    video_path = str(settings.RENDER_DIR / video_filename) if video_filename else None
    if video_path and not os.path.exists(video_path) and video_filename:
        subdir_path = str(settings.RENDER_DIR / job.id / video_filename)
        if os.path.exists(subdir_path):
            video_path = subdir_path

    if not video_path or not os.path.exists(video_path):
        raise HTTPException(status_code=404, detail="Video file not found")

    if req.auto_metadata and not req.title:
        metadata = await generate_metadata(
            topic=req.topic,
            niche=req.niche,
            title_override=req.title,
        )
        title = metadata.title
        description = metadata.description
        tags = metadata.tags
    else:
        title = req.title or f"{req.topic} video"
        description = req.description or ""
        tags = req.tags or []

    thumb_path = str(settings.RENDER_DIR / f"{job.id}_yt_thumb.jpg")
    generate_thumbnail(video_path, title, req.niche, thumb_path)
    if not os.path.exists(thumb_path):
        thumb_path = None

    upload_record = YouTubeUpload(
        id=str(uuid.uuid4()),
        render_output_id=req.render_output_id,
        title=title,
        description=description,
        tags=json.dumps(tags),
        thumbnail_path=thumb_path,
        privacy_status=req.privacy_status,
        playlist_id=req.playlist_id,
        scheduled_time=req.schedule_time,
        status="pending",
    )
    db.add(upload_record)
    try:
        db.commit()
        db.refresh(upload_record)
    except Exception:
        db.rollback()
        raise

    upload_id = upload_record.id

    upload_job = await uploader.queue_upload(
        render_output_id=req.render_output_id,
        video_path=video_path,
        niche=req.niche,
        topic=req.topic,
        auto_metadata=False,
        title_override=title,
        description_override=description,
        tags_override=tags,
        privacy_status=req.privacy_status,
        playlist_id=req.playlist_id,
        scheduled_time=req.schedule_time,
        upload_id=upload_id,
    )

    record = db.query(YouTubeUpload).filter(YouTubeUpload.id == upload_id).first()
    if record:
        record.status = "queued"
        try:
            db.commit()
        except Exception:
            db.rollback()

    return YouTubeUploadResponse(
        id=upload_id,
        title=title,
        description=description,
        tags=tags,
        thumbnail_path=thumb_path,
        privacy_status=req.privacy_status,
        status="queued",
    )


@router.post("/direct-upload", response_model=YouTubeUploadResponse)
async def direct_upload_video(
    video: UploadFile = File(...),
    privacy_status: str = Form(default="public"),
    playlist_id: str | None = Form(default=None),
    auto_metadata: bool = Form(default=True),
    title: str | None = Form(default=None),
    description: str | None = Form(default=None),
    tags: str | None = Form(default=None),
    niche: str = Form(default="psychology"),
    topic: str = Form(default=""),
    db: Session = Depends(get_db),
):
    """Upload a video file directly to YouTube (drag and drop)."""
    cred = (
        db.query(YouTubeCredential).filter(YouTubeCredential.is_active == True).first()
    )
    if not cred:
        raise HTTPException(
            status_code=400,
            detail="YouTube not connected. Visit /api/youtube/auth first.",
        )

    if uploader.quota_exceeded:
        pending = len(uploader.quota_queue)
        raise HTTPException(
            status_code=429,
            detail=f"YouTube upload quota exceeded. {pending} videos pending retry. Quota resets at midnight Pacific Time.",
        )

    if not video.filename:
        raise HTTPException(status_code=400, detail="No video file provided")

    allowed_exts = {".mp4", ".mov", ".avi", ".wmv", ".flv", ".webm", ".mkv", ".m4v"}
    ext = os.path.splitext(video.filename)[1].lower()
    if ext not in allowed_exts:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported video format: {ext}. Allowed: {', '.join(allowed_exts)}",
        )

    upload_dir = settings.RENDER_DIR / "yt_direct_uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)

    job_id = uuid.uuid4().hex[:12]
    temp_filename = f"{job_id}{ext}"
    temp_path = str(upload_dir / temp_filename)

    try:
        with open(temp_path, "wb") as buffer:
            shutil.copyfileobj(video.file, buffer)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save video file: {e}")

    file_size = os.path.getsize(temp_path)
    if file_size > 128 * 1024 * 1024:
        os.remove(temp_path)
        raise HTTPException(status_code=400, detail="Video file too large")

    if auto_metadata and not title:
        metadata = await generate_metadata(
            topic=topic, niche=niche, title_override=title
        )
        final_title = metadata.title
        final_description = metadata.description
        final_tags = metadata.tags
    else:
        final_title = title or os.path.splitext(video.filename)[0]
        final_description = description or ""
        final_tags = json.loads(tags) if tags else []

    thumb_path = str(upload_dir / f"{job_id}_yt_thumb.jpg")
    generate_thumbnail(temp_path, final_title, niche, thumb_path)
    if not os.path.exists(thumb_path):
        thumb_path = None

    upload_record = YouTubeUpload(
        id=job_id,
        render_output_id=f"direct_{job_id}",
        title=final_title,
        description=final_description,
        tags=json.dumps(final_tags),
        thumbnail_path=thumb_path,
        privacy_status=privacy_status,
        playlist_id=playlist_id,
        status="pending",
    )
    db.add(upload_record)
    try:
        db.commit()
        db.refresh(upload_record)
    except Exception:
        db.rollback()
        os.remove(temp_path)
        raise

    upload_job = await uploader.queue_upload(
        render_output_id=f"direct_{job_id}",
        video_path=temp_path,
        niche=niche,
        topic=topic,
        auto_metadata=False,
        title_override=final_title,
        description_override=final_description,
        tags_override=final_tags,
        privacy_status=privacy_status,
        playlist_id=playlist_id,
    )

    return YouTubeUploadResponse(
        id=job_id,
        title=final_title,
        description=final_description,
        tags=final_tags,
        thumbnail_path=thumb_path,
        privacy_status=privacy_status,
        status="queued",
    )


@router.get("/uploads", response_model=YouTubeUploadListResponse)
async def list_uploads(
    limit: int = 50,
    status: str | None = None,
    db: Session = Depends(get_db),
):
    q = db.query(YouTubeUpload).order_by(YouTubeUpload.created_at.desc())
    if status:
        q = q.filter(YouTubeUpload.status == status)
    items = q.limit(limit).all()
    return YouTubeUploadListResponse(
        items=[
            YouTubeUploadResponse(
                id=u.id,
                video_id=u.video_id,
                video_url=u.video_url,
                title=u.title,
                description=u.description,
                tags=json.loads(u.tags) if u.tags else [],
                thumbnail_path=u.thumbnail_path,
                privacy_status=u.privacy_status,
                status=u.status,
                error_message=u.error_message,
                created_at=u.created_at.isoformat() if u.created_at else None,
                uploaded_at=u.uploaded_at.isoformat() if u.uploaded_at else None,
            )
            for u in items
        ],
        total=len(items),
    )


@router.get("/uploads/{upload_id}", response_model=YouTubeUploadResponse)
async def get_upload(upload_id: str, db: Session = Depends(get_db)):
    u = db.query(YouTubeUpload).filter(YouTubeUpload.id == upload_id).first()
    if not u:
        raise HTTPException(status_code=404, detail="Upload not found")
    return YouTubeUploadResponse(
        id=u.id,
        video_id=u.video_id,
        video_url=u.video_url,
        title=u.title,
        description=u.description,
        tags=json.loads(u.tags) if u.tags else [],
        thumbnail_path=u.thumbnail_path,
        privacy_status=u.privacy_status,
        status=u.status,
        error_message=u.error_message,
        created_at=u.created_at.isoformat() if u.created_at else None,
        uploaded_at=u.uploaded_at.isoformat() if u.uploaded_at else None,
    )


@router.delete("/uploads/{upload_id}")
async def delete_upload(upload_id: str, db: Session = Depends(get_db)):
    u = db.query(YouTubeUpload).filter(YouTubeUpload.id == upload_id).first()
    if not u:
        raise HTTPException(status_code=404, detail="Upload not found")
    db.delete(u)
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise
    return {"message": "Upload deleted"}


# ─────────────────────────────────────────────────────
# Playlists
# ─────────────────────────────────────────────────────


@router.get("/playlists")
async def list_playlists(db: Session = Depends(get_db)):
    cred = (
        db.query(YouTubeCredential).filter(YouTubeCredential.is_active == True).first()
    )
    if not cred:
        raise HTTPException(status_code=400, detail="YouTube not connected")

    try:
        access_token = decrypt_token(cred.access_token)
        refresh_token = decrypt_token(cred.refresh_token)
    except Exception as e:
        log.error(
            "[YT] Stored YouTube tokens cannot be decrypted: %s: %s",
            type(e).__name__,
            e or repr(e),
        )
        raise HTTPException(
            status_code=400,
            detail="Stored YouTube credentials are unreadable. "
            "Re-authorize at /api/youtube/auth",
        )

    client = YouTubeClient(
        access_token=access_token,
        refresh_token=refresh_token,
        client_id=cred.client_id,
        client_secret=cred.client_secret,
        token_expiry=cred.token_expiry,
    )
    try:
        playlists = await client.list_playlists()
    except Exception as e:
        log.error(f"[YT] Failed to list playlists: {e}")
        raise HTTPException(
            status_code=502, detail=f"YouTube API error: {e}"
        )
    return [
        {
            "id": p["id"],
            "title": p["snippet"]["title"],
            "video_count": p["contentDetails"]["itemCount"],
        }
        for p in playlists
    ]


# ─────────────────────────────────────────────────────
# Queue management
# ─────────────────────────────────────────────────────


@router.get("/queue")
async def get_queue():
    return {
        "queue_size": len(uploader.queue),
        "active_uploads": uploader.active_uploads,
        "quota_exceeded": uploader.quota_exceeded,
        "quota_queue_size": len(uploader.quota_queue),
        "jobs": [
            {
                "id": j.id,
                "title": j.title,
                "status": j.status,
                "attempt": j.attempt,
            }
            for j in uploader.queue
        ],
        "quota_pending": [
            {
                "title": q["title"],
                "queued_at": q["queued_at"],
            }
            for q in uploader.quota_queue
        ],
    }
