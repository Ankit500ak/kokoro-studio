import logging
import os
from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session
from typing import Optional
import uuid

from ..core.database import get_db
from ..core.models import Project, GeneratedAudio, RenderJob, RenderOutput
from ..core.config import settings
from ..schemas.project import ProjectCreate, ProjectUpdate, ProjectResponse, ProjectListResponse

log = logging.getLogger(__name__)

router = APIRouter(prefix="/projects", tags=["projects"])


@router.get("/", response_model=ProjectListResponse)
async def list_projects(db: Session = Depends(get_db)):
    projects = db.query(Project).order_by(Project.created_at.desc()).all()
    return ProjectListResponse(
        items=[ProjectResponse.model_validate(p) for p in projects],
        total=len(projects),
    )


@router.post("/", response_model=ProjectResponse)
async def create_project(req: ProjectCreate, db: Session = Depends(get_db)):
    project = Project(
        id=str(uuid.uuid4()),
        name=req.name,
        title=req.title,
        script_text=req.script_text,
    )
    db.add(project)
    try:
        db.commit()
        db.refresh(project)
    except Exception as e:
        db.rollback()
        log.exception("Failed to create project")
        raise HTTPException(status_code=500, detail="Failed to create project")
    return ProjectResponse.model_validate(project)


@router.get("/{project_id}", response_model=ProjectResponse)
async def get_project(project_id: str, db: Session = Depends(get_db)):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return ProjectResponse.model_validate(project)


@router.patch("/{project_id}", response_model=ProjectResponse)
async def update_project(project_id: str, req: ProjectUpdate, db: Session = Depends(get_db)):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    try:
        update_data = req.model_dump(exclude_unset=True)
        for key, value in update_data.items():
            setattr(project, key, value)
        db.commit()
    except Exception as e:
        db.rollback()
        log.exception("Failed to update project")
        raise HTTPException(status_code=500, detail="Update failed")
    return ProjectResponse.model_validate(project)


@router.delete("/{project_id}")
async def delete_project(project_id: str, db: Session = Depends(get_db)):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # Collect files to delete after DB commit
    files_to_delete = []

    # Find audio files
    audio_files = db.query(GeneratedAudio).filter(GeneratedAudio.project_id == project_id).all()
    for audio in audio_files:
        filepath = settings.AUDIO_DIR / audio.filename
        if filepath.exists():
            files_to_delete.append(filepath)

    # Find render outputs (video + thumbnail files)
    render_jobs = db.query(RenderJob).filter(RenderJob.project_id == project_id).all()
    for job in render_jobs:
        output = db.query(RenderOutput).filter(RenderOutput.render_job_id == job.id).first()
        if output:
            if output.video_filename:
                vpath = settings.RENDER_DIR / output.video_filename
                if vpath.exists():
                    files_to_delete.append(vpath)
                # Also check subdirectory
                vpath_sub = settings.RENDER_DIR / job.id / output.video_filename
                if vpath_sub.exists():
                    files_to_delete.append(vpath_sub)
            if output.thumbnail_filename:
                tpath = settings.RENDER_DIR / output.thumbnail_filename
                if tpath.exists():
                    files_to_delete.append(tpath)
                tpath_sub = settings.RENDER_DIR / job.id / output.thumbnail_filename
                if tpath_sub.exists():
                    files_to_delete.append(tpath_sub)
        # ASS file
        ass_path = settings.RENDER_DIR / f"{job.id}.ass"
        if ass_path.exists():
            files_to_delete.append(ass_path)

    try:
        db.delete(project)
        db.commit()
    except Exception as e:
        db.rollback()
        log.exception("Failed to delete project")
        raise HTTPException(status_code=500, detail="Delete failed")

    # Clean up files after successful DB commit
    for f in files_to_delete:
        try:
            os.remove(f)
        except OSError as e:
            log.warning(f"Failed to delete file {f}: {e}")

    return {"deleted": True}
