import logging
from fastapi import APIRouter, HTTPException, Depends, UploadFile, File
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from typing import Optional
import uuid
import os
import subprocess
import json
import asyncio

from ..core.database import get_db
from ..core.models import VideoAsset
from ..core.config import settings
from ..schemas.video import VideoAssetResponse, VideoAssetListResponse, VideoAssetUpdate

log = logging.getLogger(__name__)

router = APIRouter(prefix="/media", tags=["media"])

MAX_UPLOAD_SIZE = 500 * 1024 * 1024  # 500MB


def probe_video(filepath: str) -> dict:
    """Use FFprobe to get video metadata."""
    try:
        cmd = [
            "ffprobe",
            "-v", "quiet",
            "-print_format", "json",
            "-show_format",
            "-show_streams",
            filepath
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode == 0:
            return json.loads(result.stdout)
    except (subprocess.TimeoutExpired, FileNotFoundError, json.JSONDecodeError):
        pass
    return {}


def resolve_asset_file(asset) -> Optional[str]:
    """Return the on-disk path of an asset, or None if the file is gone."""
    real_media = settings.MEDIA_DIR.resolve()

    candidates = [settings.MEDIA_DIR / asset.filename]
    if asset.folder:
        candidates.append(settings.MEDIA_DIR / asset.folder / asset.filename)
        candidates.append(settings.MEDIA_DIR / asset.folder / os.path.basename(asset.filename))
    if asset.storage_key:
        candidates.append(settings.MEDIA_DIR / asset.storage_key)

    for candidate in candidates:
        try:
            real_path = candidate.resolve()
        except OSError:
            continue
        if candidate.is_file() and str(real_path).startswith(str(real_media)):
            return str(candidate)
    return None


@router.get("/", response_model=VideoAssetListResponse)
async def list_video_assets(
    category: Optional[str] = None,
    folder: Optional[str] = None,
    search: Optional[str] = None,
    db: Session = Depends(get_db),
):
    query = db.query(VideoAsset).filter(VideoAsset.status == "ready")

    if category:
        query = query.filter(VideoAsset.category == category)
    if folder:
        query = query.filter(VideoAsset.folder == folder)
    if search:
        query = query.filter(VideoAsset.original_name.contains(search))

    items = query.order_by(VideoAsset.created_at.desc()).all()
    return VideoAssetListResponse(
        items=[VideoAssetResponse.model_validate(v) for v in items],
        total=len(items),
    )


@router.get("/folders")
async def list_video_folders(db: Session = Depends(get_db)):
    """List all available video folders with clip counts and a thumbnail."""
    rows = (
        db.query(VideoAsset)
        .filter(VideoAsset.status == "ready", VideoAsset.folder.isnot(None))
        .order_by(VideoAsset.folder, VideoAsset.id)
        .all()
    )

    folders: dict = {}
    for asset in rows:
        info = folders.setdefault(asset.folder, {"count": 0, "thumbnail_asset_id": None})
        info["count"] += 1
        # Skip assets whose file was deleted so the card still gets a preview.
        if info["thumbnail_asset_id"] is None and resolve_asset_file(asset):
            info["thumbnail_asset_id"] = asset.id

    return [
        {"name": name, "count": info["count"], "thumbnail_asset_id": info["thumbnail_asset_id"]}
        for name, info in folders.items()
    ]


@router.post("/upload", response_model=VideoAssetResponse)
async def upload_video(file: UploadFile = File(...), db: Session = Depends(get_db)):
    if not file.content_type or not file.content_type.startswith("video/"):
        raise HTTPException(status_code=400, detail="File must be a video")

    asset_id = str(uuid.uuid4())
    ext = os.path.splitext(file.filename or "video.mp4")[1]
    filename = f"{asset_id}{ext}"
    filepath = settings.MEDIA_DIR / filename

    content = None
    try:
        content = await file.read()
        if len(content) > MAX_UPLOAD_SIZE:
            raise HTTPException(status_code=413, detail="File too large (max 500MB)")

        with open(filepath, "wb") as f:
            f.write(content)
    except HTTPException:
        raise
    except Exception as e:
        log.exception("Failed to save uploaded file")
        if filepath.exists():
            try:
                os.remove(filepath)
            except OSError:
                pass
        raise HTTPException(status_code=500, detail="File upload failed")

    try:
        probe_data = await asyncio.to_thread(probe_video, str(filepath))
        video_stream = None
        for stream in probe_data.get("streams", []):
            if stream.get("codec_type") == "video":
                video_stream = stream
                break

        duration = None
        width = None
        height = None
        fps = None
        codec = None

        if video_stream:
            width = video_stream.get("width")
            height = video_stream.get("height")
            codec = video_stream.get("codec_name")

            r_frame_rate = video_stream.get("r_frame_rate", "30/1")
            if "/" in r_frame_rate:
                num, den = r_frame_rate.split("/")
                try:
                    fps = round(int(num) / int(den), 2)
                except (ValueError, ZeroDivisionError):
                    fps = 30.0
            else:
                try:
                    fps = float(r_frame_rate)
                except ValueError:
                    fps = 30.0

        fmt = probe_data.get("format", {})
        if fmt.get("duration"):
            try:
                duration = float(fmt["duration"])
            except ValueError:
                pass

        asset = VideoAsset(
            id=asset_id,
            filename=filename,
            original_name=file.filename,
            storage_key=f"media/{filename}",
            duration=duration,
            width=width,
            height=height,
            fps=fps,
            codec=codec,
            file_size=len(content) if content else 0,
        )
        db.add(asset)
        db.commit()

        return VideoAssetResponse.model_validate(asset)
    except Exception as e:
        db.rollback()
        if filepath.exists():
            try:
                os.remove(filepath)
            except OSError:
                pass
        log.exception("Failed to process uploaded video")
        raise HTTPException(status_code=500, detail="Video processing failed")


@router.get("/{asset_id}", response_model=VideoAssetResponse)
async def get_video_asset(asset_id: str, db: Session = Depends(get_db)):
    asset = db.query(VideoAsset).filter(VideoAsset.id == asset_id).first()
    if not asset:
        raise HTTPException(status_code=404, detail="Video asset not found")
    return VideoAssetResponse.model_validate(asset)


@router.get("/{asset_id}/file")
async def get_video_file(asset_id: str, db: Session = Depends(get_db)):
    asset = db.query(VideoAsset).filter(VideoAsset.id == asset_id).first()
    if not asset:
        raise HTTPException(status_code=404, detail="Video asset not found")

    filepath = resolve_asset_file(asset)
    if not filepath:
        raise HTTPException(status_code=404, detail="Video file not found")

    return FileResponse(filepath, media_type="video/mp4")


@router.get("/{asset_id}/thumbnail")
async def get_video_thumbnail(asset_id: str, db: Session = Depends(get_db)):
    """Generate and return a JPEG thumbnail for a video asset."""
    asset = db.query(VideoAsset).filter(VideoAsset.id == asset_id).first()
    if not asset:
        raise HTTPException(status_code=404, detail="Video asset not found")

    filepath = resolve_asset_file(asset)
    if not filepath:
        raise HTTPException(status_code=404, detail="Video file not found")

    # Generate thumbnail with ffmpeg
    thumb_dir = settings.MEDIA_DIR / "_thumbs"
    thumb_dir.mkdir(exist_ok=True)
    thumb_path = thumb_dir / f"{asset_id}.jpg"

    if not thumb_path.exists():
        try:
            cmd = [
                "ffmpeg", "-y",
                "-i", str(filepath),
                "-ss", "00:00:01",
                "-vframes", "1",
                "-vf", "scale=320:-1",
                str(thumb_path)
            ]
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await proc.communicate()
            if proc.returncode != 0:
                log.warning(f"ffmpeg thumbnail failed for {asset_id}: {stderr.decode()[:200]}")
        except Exception as e:
            log.warning(f"Failed to generate thumbnail for {asset_id}: {e}")
            raise HTTPException(status_code=500, detail="Thumbnail generation failed")

    if not thumb_path.exists():
        raise HTTPException(status_code=500, detail="Thumbnail not generated")

    return FileResponse(thumb_path, media_type="image/jpeg")


@router.patch("/{asset_id}", response_model=VideoAssetResponse)
async def update_video_asset(asset_id: str, req: VideoAssetUpdate, db: Session = Depends(get_db)):
    asset = db.query(VideoAsset).filter(VideoAsset.id == asset_id).first()
    if not asset:
        raise HTTPException(status_code=404, detail="Video asset not found")

    try:
        update_data = req.model_dump(exclude_unset=True)
        for key, value in update_data.items():
            setattr(asset, key, value)
        db.commit()
        return VideoAssetResponse.model_validate(asset)
    except Exception as e:
        db.rollback()
        log.exception("Failed to update video asset")
        raise HTTPException(status_code=500, detail=f"Update failed: {e}")


@router.delete("/{asset_id}")
async def delete_video_asset(asset_id: str, db: Session = Depends(get_db)):
    asset = db.query(VideoAsset).filter(VideoAsset.id == asset_id).first()
    if not asset:
        raise HTTPException(status_code=404, detail="Video asset not found")

    try:
        db.delete(asset)
        db.commit()
    except Exception as e:
        db.rollback()
        log.exception("Failed to delete video asset from DB")
        raise HTTPException(status_code=500, detail=f"Delete failed: {e}")

    filepath = settings.MEDIA_DIR / asset.filename
    if filepath.exists():
        try:
            os.remove(filepath)
        except OSError as e:
            log.warning(f"Failed to delete file {filepath}: {e}")

    return {"deleted": True}


@router.post("/scan")
async def scan_media_directory(
    remove_missing: bool = False,
    db: Session = Depends(get_db),
):
    """Scan media directory (including subdirectories) and register any unregistered videos."""
    registered = 0
    skipped = 0
    missing = []
    
    # Get all existing filenames in DB
    existing = {a.filename for a in db.query(VideoAsset.filename).all()}
    
    # Walk through media directory
    for root, dirs, files in os.walk(str(settings.MEDIA_DIR)):
        for filename in files:
            # Only process video files
            if not filename.lower().endswith(('.mp4', '.mov', '.avi', '.mkv', '.webm')):
                continue
            
            # Get relative path from settings.MEDIA_DIR
            full_path = os.path.join(root, filename)
            rel_path = os.path.relpath(full_path, str(settings.MEDIA_DIR))
            
            # Skip if already registered
            if rel_path in existing:
                skipped += 1
                continue
            
            # Probe video for metadata, then register. Each file commits on its
            # own so one bad/interrupted row cannot abort the whole scan.
            try:
                probe = probe_video(full_path)
                duration = None
                width = None
                height = None

                if probe:
                    fmt = probe.get("format", {})
                    duration = (
                        float(fmt.get("duration", 0))
                        if fmt.get("duration")
                        else None
                    )

                    for stream in probe.get("streams", []):
                        if stream.get("codec_type") == "video":
                            width = stream.get("width")
                            height = stream.get("height")
                            break

                # Extract folder from subdirectory name (e.g. "odlysatisfy/001.mp4" -> "odlysatisfy")
                folder_name = (
                    os.path.dirname(rel_path)
                    if os.sep in rel_path or "/" in rel_path
                    else None
                )
                asset = VideoAsset(
                    id=str(uuid.uuid4()),
                    filename=rel_path,
                    original_name=filename,
                    storage_key=rel_path,
                    file_size=os.path.getsize(full_path),
                    duration=duration,
                    width=width,
                    height=height,
                    status="ready",
                    category="stock",
                    folder=folder_name,
                )
                db.add(asset)
                db.commit()
                registered += 1
            except Exception as e:
                db.rollback()
                log.warning(f"Failed to register {rel_path}: {e}")

    # Rows whose file no longer exists on disk (deleted/renamed outside the app).
    for asset in db.query(VideoAsset).filter(VideoAsset.status == "ready").all():
        if resolve_asset_file(asset) is None:
            missing.append(asset.id)
            if remove_missing:
                db.delete(asset)
    if remove_missing and missing:
        db.commit()

    return {
        "registered": registered,
        "skipped": skipped,
        "missing": missing,
        "removed_missing": len(missing) if remove_missing else 0,
        "message": (
            f"Scanned media directory. Registered {registered} new videos, "
            f"skipped {skipped} existing, {len(missing)} missing files."
        ),
    }
