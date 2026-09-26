from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


class YouTubeUploadRequest(BaseModel):
    render_output_id: str = Field(..., description="Render output ID to upload")
    privacy_status: str = Field(default="public", pattern="^(public|unlisted|private)$")
    playlist_id: Optional[str] = Field(default=None, description="YouTube playlist ID")
    schedule_time: Optional[datetime] = Field(default=None, description="Schedule publish time (requires private)")
    auto_metadata: bool = Field(default=True, description="Auto-generate title, desc, tags")
    title: Optional[str] = Field(default=None, max_length=100, description="Override auto-generated title")
    description: Optional[str] = Field(default=None, max_length=5000, description="Override auto-generated description")
    tags: Optional[list[str]] = Field(default=None, description="Override auto-generated tags")
    niche: str = Field(default="psychology", max_length=50, description="Content niche for metadata generation")
    topic: str = Field(default="", max_length=500, description="Topic for metadata generation")


class MetadataPreviewRequest(BaseModel):
    render_output_id: str
    niche: str = "psychology"
    topic: str = ""
    title_override: Optional[str] = None


class YouTubeUploadResponse(BaseModel):
    id: str
    video_id: Optional[str] = None
    video_url: Optional[str] = None
    title: str
    description: Optional[str] = None
    tags: list[str] = []
    thumbnail_path: Optional[str] = None
    privacy_status: str
    status: str
    error_message: Optional[str] = None
    created_at: Optional[str] = None
    uploaded_at: Optional[str] = None


class YouTubeUploadListResponse(BaseModel):
    items: list[YouTubeUploadResponse]
    total: int


class MetadataPreviewResponse(BaseModel):
    title: str
    description: str
    tags: list[str]
    hashtags: list[str]
    title_options: list[str]
    category_id: str


class YouTubeAuthResponse(BaseModel):
    auth_url: str
    message: str


class YouTubeStatusResponse(BaseModel):
    connected: bool
    channel_title: Optional[str] = None
    channel_id: Optional[str] = None
    expires_at: Optional[str] = None


class DirectUploadRequest(BaseModel):
    privacy_status: str = Field(default="public", pattern="^(public|unlisted|private)$")
    playlist_id: Optional[str] = Field(default=None)
    schedule_time: Optional[datetime] = Field(default=None)
    auto_metadata: bool = Field(default=True)
    title: Optional[str] = Field(default=None, max_length=100)
    description: Optional[str] = Field(default=None, max_length=5000)
    tags: Optional[list[str]] = Field(default=None)
    niche: str = Field(default="psychology", max_length=50)
    topic: str = Field(default="", max_length=500)
