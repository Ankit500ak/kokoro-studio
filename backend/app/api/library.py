import logging
from fastapi import APIRouter, HTTPException, Depends, Query
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from sqlalchemy import desc, func
from typing import Optional
import os

from ..core.database import get_db
from ..core.models import GeneratedAudio
from ..core.config import settings
from ..schemas.library import (
    AudioItem, AudioListResponse, AudioDeleteResponse, AudioStatsResponse
)

log = logging.getLogger(__name__)

router = APIRouter(prefix="/library", tags=["library"])


@router.get("/", response_model=AudioListResponse)
async def list_audio(
    voice: Optional[str] = Query(None, description="Filter by voice"),
    preset: Optional[str] = Query(None, description="Filter by preset"),
    mode: Optional[str] = Query(None, description="Filter by mode"),
    search: Optional[str] = Query(None, description="Search in text content"),
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    query = db.query(GeneratedAudio)

    if voice:
        query = query.filter(GeneratedAudio.voice == voice)
    if preset:
        query = query.filter(GeneratedAudio.preset == preset)
    if mode:
        query = query.filter(GeneratedAudio.mode == mode)
    if search:
        query = query.filter(GeneratedAudio.text.contains(search))

    total = query.count()
    items = (
        query
        .order_by(desc(GeneratedAudio.created_at))
        .offset((page - 1) * per_page)
        .limit(per_page)
        .all()
    )

    return AudioListResponse(
        items=[AudioItem.model_validate(item) for item in items],
        total=total,
        page=page,
        per_page=per_page,
    )


@router.get("/stats", response_model=AudioStatsResponse)
async def get_stats(db: Session = Depends(get_db)):
    total = db.query(GeneratedAudio).count()
    total_duration = db.query(
        func.sum(GeneratedAudio.duration)
    ).scalar() or 0.0

    voices_used = (
        db.query(GeneratedAudio.voice)
        .distinct()
        .all()
    )

    return AudioStatsResponse(
        total_generated=total,
        total_duration_seconds=round(total_duration, 2),
        unique_voices=len(voices_used),
        voices_used=[v[0] for v in voices_used],
    )


@router.get("/{audio_id}", response_model=AudioItem)
async def get_audio(audio_id: str, db: Session = Depends(get_db)):
    item = db.query(GeneratedAudio).filter(GeneratedAudio.id == audio_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Audio not found")
    return AudioItem.model_validate(item)


@router.get("/{audio_id}/file")
async def get_audio_file(audio_id: str, db: Session = Depends(get_db)):
    item = db.query(GeneratedAudio).filter(GeneratedAudio.id == audio_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Audio not found")

    filepath = settings.AUDIO_DIR / item.filename
    if not filepath.exists():
        raise HTTPException(status_code=404, detail="Audio file not found on disk")

    return FileResponse(filepath, media_type="audio/wav", filename=item.filename)


@router.delete("/{audio_id}", response_model=AudioDeleteResponse)
async def delete_audio(audio_id: str, db: Session = Depends(get_db)):
    item = db.query(GeneratedAudio).filter(GeneratedAudio.id == audio_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Audio not found")

    filepath = settings.AUDIO_DIR / item.filename

    try:
        db.delete(item)
        db.commit()
    except Exception as e:
        db.rollback()
        log.exception("Failed to delete audio from DB")
        raise HTTPException(status_code=500, detail=f"Delete failed: {e}")

    # File cleanup after successful DB commit
    if filepath.exists():
        try:
            os.remove(filepath)
        except OSError as e:
            log.warning(f"Failed to delete file {filepath}: {e}")

    return AudioDeleteResponse(id=audio_id, deleted=True)
