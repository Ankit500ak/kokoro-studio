from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime


class RenderJobCreate(BaseModel):
    project_id: str
    generated_audio_id: str
    video_folders: Optional[List[str]] = None


class RenderJobResponse(BaseModel):
    id: str
    project_id: str
    generated_audio_id: Optional[str] = None
    status: str
    progress: int = 0
    current_stage: Optional[str] = None
    error_code: Optional[str] = None
    error_message: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    created_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class RenderJobListResponse(BaseModel):
    items: List[RenderJobResponse]
    total: int


class RenderOutputResponse(BaseModel):
    id: str
    render_job_id: str
    video_filename: Optional[str] = None
    thumbnail_filename: Optional[str] = None
    duration: Optional[float] = None
    width: Optional[int] = None
    height: Optional[int] = None
    file_size: Optional[int] = None
    codec: Optional[str] = None
    created_at: Optional[datetime] = None

    model_config = {"from_attributes": True}
