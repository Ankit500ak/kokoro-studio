from pydantic import BaseModel
from typing import Optional, List, Any
from datetime import datetime


class TemplateCreate(BaseModel):
    name: str
    description: Optional[str] = None
    config: dict  # JSON config for the template


class TemplateUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    config: Optional[dict] = None


class TemplateResponse(BaseModel):
    id: str
    name: str
    version: int
    description: Optional[str] = None
    aspect_ratio: str
    resolution_width: int
    resolution_height: int
    fps: int
    config: Any  # JSON config
    is_default: bool
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class TemplateListResponse(BaseModel):
    items: List[TemplateResponse]
    total: int
