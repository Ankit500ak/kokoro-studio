from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime


class VideoAssetResponse(BaseModel):
    id: str
    filename: str
    original_name: Optional[str] = None
    storage_key: str
    duration: Optional[float] = None
    width: Optional[int] = None
    height: Optional[int] = None
    fps: Optional[float] = None
    codec: Optional[str] = None
    file_size: Optional[int] = None
    tags: Optional[str] = None
    category: Optional[str] = None
    folder: Optional[str] = None
    usage_count: int = 0
    last_used_at: Optional[datetime] = None
    status: str = "ready"
    created_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class VideoAssetListResponse(BaseModel):
    items: List[VideoAssetResponse]
    total: int


class VideoAssetUpdate(BaseModel):
    tags: Optional[str] = None
    category: Optional[str] = None
