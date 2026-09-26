import logging
from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from typing import Optional
import uuid
import os
from datetime import datetime, timedelta, timezone

from ..core.database import get_db, SessionLocal
from ..core.models import RenderJob, RenderOutput, GeneratedAudio
from ..core.config import settings
from ..schemas.render import RenderJobCreate, RenderJobResponse, RenderJobListResponse, RenderOutputResponse

log = logging.getLogger(__name__)

router = APIRouter(prefix="/renders", tags=["renders"])


@router.get("/", response_model=RenderJobListResponse)
async def list_render_jobs(
    project_id: Optional[str] = None,
    status: Optional[str] = None,
    db: Session = Depends(get_db),
):
    stale_before = datetime.now(timezone.utc) - timedelta(minutes=30)
    db.query(RenderJob).filter(
        RenderJob.status.in_(["queued", "rendering"]),
        RenderJob.created_at < stale_before,
    ).update(
        {
            RenderJob.status: "failed",
            RenderJob.error_code: "stale_job",
            RenderJob.error_message: "Render job exceeded the stale-job timeout",
        },
        synchronize_session=False,
    )
    db.commit()
    query = db.query(RenderJob)

    if project_id:
        query = query.filter(RenderJob.project_id == project_id)
    if status:
        query = query.filter(RenderJob.status == status)

    items = query.order_by(RenderJob.created_at.desc()).all()

    return RenderJobListResponse(
        items=[RenderJobResponse.model_validate(r) for r in items],
        total=len(items),
    )


@router.post("/", response_model=RenderJobResponse)
async def create_render_job(req: RenderJobCreate, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    audio = db.query(GeneratedAudio).filter(GeneratedAudio.id == req.generated_audio_id).first()
    if not audio:
        raise HTTPException(status_code=404, detail="Audio not found")

    job = RenderJob(
        id=str(uuid.uuid4()),
        project_id=req.project_id,
        generated_audio_id=req.generated_audio_id,
        video_folder=",".join(req.video_folders) if req.video_folders else None,
        status="queued",
    )
    db.add(job)
    try:
        db.commit()
    except Exception as e:
        db.rollback()
        log.exception("Failed to create render job")
        raise HTTPException(status_code=500, detail=f"Failed to create job: {e}")

    background_tasks.add_task(run_render_job, job.id)

    return RenderJobResponse.model_validate(job)


@router.get("/{job_id}", response_model=RenderJobResponse)
async def get_render_job(job_id: str, db: Session = Depends(get_db)):
    job = db.query(RenderJob).filter(RenderJob.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Render job not found")
    return RenderJobResponse.model_validate(job)


@router.get("/{job_id}/output", response_model=RenderOutputResponse)
async def get_render_output(job_id: str, db: Session = Depends(get_db)):
    job = db.query(RenderJob).filter(RenderJob.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Render job not found")

    output = db.query(RenderOutput).filter(RenderOutput.render_job_id == job_id).first()
    if not output:
        raise HTTPException(status_code=404, detail="Render output not ready")

    return RenderOutputResponse.model_validate(output)


@router.get("/{job_id}/file")
async def get_render_file(job_id: str, db: Session = Depends(get_db)):
    output = db.query(RenderOutput).filter(RenderOutput.render_job_id == job_id).first()
    if not output or not output.video_filename:
        raise HTTPException(status_code=404, detail="Render output not found")

    # Check in subdirectory first (renders/{job_id}/{filename}), then root (renders/{filename})
    filepath_subdir = settings.RENDER_DIR / job_id / output.video_filename
    filepath_root = settings.RENDER_DIR / output.video_filename
    
    real_render = settings.RENDER_DIR.resolve()
    
    if filepath_subdir.exists() and str(filepath_subdir.resolve()).startswith(str(real_render)):
        return FileResponse(filepath_subdir, media_type="video/mp4", filename=output.video_filename)
    elif filepath_root.exists() and str(filepath_root.resolve()).startswith(str(real_render)):
        return FileResponse(filepath_root, media_type="video/mp4", filename=output.video_filename)
    else:
        raise HTTPException(status_code=404, detail="Video file not found")


@router.get("/{job_id}/thumbnail")
async def get_render_thumbnail(job_id: str, db: Session = Depends(get_db)):
    output = db.query(RenderOutput).filter(RenderOutput.render_job_id == job_id).first()
    if not output or not output.thumbnail_filename:
        raise HTTPException(status_code=404, detail="Thumbnail not found")

    # Check in subdirectory first, then root
    filepath_subdir = settings.RENDER_DIR / job_id / output.thumbnail_filename
    filepath_root = settings.RENDER_DIR / output.thumbnail_filename
    
    real_render = settings.RENDER_DIR.resolve()
    
    if filepath_subdir.exists() and str(filepath_subdir.resolve()).startswith(str(real_render)):
        return FileResponse(filepath_subdir, media_type="image/jpeg")
    elif filepath_root.exists() and str(filepath_root.resolve()).startswith(str(real_render)):
        return FileResponse(filepath_root, media_type="image/jpeg")
    else:
        raise HTTPException(status_code=404, detail="Thumbnail file not found")


@router.post("/{job_id}/retry", response_model=RenderJobResponse)
async def retry_render_job(job_id: str, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    job = db.query(RenderJob).filter(RenderJob.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Render job not found")

    if job.status not in ("failed", "completed", "queued", "rendering"):
        raise HTTPException(status_code=400, detail="Job cannot be retried in current status")

    job.status = "queued"
    job.progress = 0
    job.current_stage = None
    job.error_code = None
    job.error_message = None
    job.started_at = None
    job.completed_at = None
    try:
        db.commit()
    except Exception as e:
        db.rollback()
        log.exception("Failed to retry render job")
        raise HTTPException(status_code=500, detail=f"Retry failed: {e}")

    background_tasks.add_task(run_render_job, job.id)

    return RenderJobResponse.model_validate(job)


@router.delete("/{job_id}")
async def delete_render_job(job_id: str, db: Session = Depends(get_db)):
    job = db.query(RenderJob).filter(RenderJob.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Render job not found")

    if job.status == "rendering":
        raise HTTPException(status_code=400, detail="Cannot delete a job that is currently rendering")

    files_to_delete = []

    output = db.query(RenderOutput).filter(RenderOutput.render_job_id == job_id).first()
    if output:
        if output.video_filename:
            # Check root
            filepath = settings.RENDER_DIR / output.video_filename
            if filepath.exists():
                files_to_delete.append(filepath)
            # Check subdirectory
            filepath_sub = settings.RENDER_DIR / job_id / output.video_filename
            if filepath_sub.exists():
                files_to_delete.append(filepath_sub)
        if output.thumbnail_filename:
            thumb_path = settings.RENDER_DIR / output.thumbnail_filename
            if thumb_path.exists():
                files_to_delete.append(thumb_path)
            thumb_sub = settings.RENDER_DIR / job_id / output.thumbnail_filename
            if thumb_sub.exists():
                files_to_delete.append(thumb_sub)
        db.delete(output)

    ass_path = settings.RENDER_DIR / f"{job_id}.ass"
    if ass_path.exists():
        files_to_delete.append(ass_path)

    # Also clean up subdirectory if it exists and is empty
    subdir = settings.RENDER_DIR / job_id
    if subdir.exists() and subdir.is_dir():
        remaining = list(subdir.iterdir())
        if not remaining:
            try:
                subdir.rmdir()
            except OSError:
                pass

    try:
        db.delete(job)
        db.commit()
    except Exception as e:
        db.rollback()
        log.exception("Failed to delete render job")
        raise HTTPException(status_code=500, detail=f"Delete failed: {e}")

    for f in files_to_delete:
        try:
            os.remove(f)
        except OSError as e:
            log.warning(f"Failed to delete file {f}: {e}")

    return {"ok": True}


def run_render_job(job_id: str):
    """Background task to render a short video."""
    from ..services.render_service import render_service

    db = SessionLocal()
    try:
        job = db.query(RenderJob).filter(RenderJob.id == job_id).first()
        if not job:
            log.error(f"Render job {job_id} not found")
            return

        render_service.execute_render(job, db)
    except Exception as e:
        log.exception(f"Render job {job_id} failed unexpectedly")
        try:
            job = db.query(RenderJob).filter(RenderJob.id == job_id).first()
            if job and job.status != "failed":
                job.status = "failed"
                job.error_code = "INTERNAL_ERROR"
                job.error_message = str(e)
                db.commit()
        except Exception:
            db.rollback()
    finally:
        db.close()
