from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime


class AudioItem(BaseModel):
    id: str
    filename: str
    voice: str
    mode: str
    preset: str
    text: str
    word_count: int
    duration: Optional[float] = None
    speed: Optional[float] = None
    tone: Optional[str] = None
    file_size: Optional[int] = None
    created_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class AudioListResponse(BaseModel):
    items: List[AudioItem]
    total: int
    page: int
    per_page: int


class AudioDeleteResponse(BaseModel):
    id: str
    deleted: bool


class AudioStatsResponse(BaseModel):
    total_generated: int
    total_duration_seconds: float
    unique_voices: int
    voices_used: List[str]
