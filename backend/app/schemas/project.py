from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime


class ProjectCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    title: Optional[str] = Field(None, max_length=500)
    script_text: Optional[str] = None


class ProjectUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=200)
    title: Optional[str] = Field(None, max_length=500)
    script_text: Optional[str] = None
    status: Optional[str] = Field(None, pattern=r"^(draft|active|completed|archived)$")


class ProjectResponse(BaseModel):
    id: str
    name: str
    title: Optional[str] = None
    script_text: Optional[str] = None
    status: str
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class ProjectListResponse(BaseModel):
    items: List[ProjectResponse]
    total: int
