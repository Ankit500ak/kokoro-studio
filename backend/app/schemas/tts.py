from pydantic import BaseModel, Field
from typing import Optional, Literal

ContentPresetId = Literal[
    "shorts",
    "storytelling",
    "mystery",
    "documentary",
    "horror",
    "romantic",
    "educational",
    "news",
]


class TTSRequest(BaseModel):
    text: str = Field(
        ..., min_length=1, max_length=50000, description="Text to synthesize"
    )
    voice: str = Field(default="am_adam", max_length=50)
    speed: float = Field(default=1.0, ge=0.5, le=2.0)
    mode: Literal["storytelling", "shorts"] = "storytelling"
    preset: ContentPresetId = "storytelling"
    tone: str = Field(default="natural", max_length=20)
    format: str = Field(default="wav", max_length=10)
    project_id: Optional[str] = Field(
        default=None, description="Link audio to a project"
    )
    tuning_id: Optional[int] = Field(
        default=None, ge=1, le=10, description="Voice tuning variation (1-10)"
    )
    use_multi_pass: bool = Field(
        default=True, description="Enable multi-pass generation for better quality"
    )
    use_enhancement: bool = Field(
        default=True, description="Enable audio enhancement pipeline"
    )
    enhancement_level: Literal["subtle", "balanced", "maximum"] = Field(
        default="balanced", description="Audio enhancement intensity"
    )


class PreviewRequest(BaseModel):
    text: str = Field(
        default="This is a voice preview for the Kokoro Studio. Listen to how natural and human this voice sounds.",
        max_length=1000,
    )
    voice: str = Field(default="am_adam", max_length=50)
    mode: Literal["storytelling", "shorts"] = "storytelling"
    tone: str = Field(default="natural", max_length=20)
    tuning_id: Optional[int] = Field(
        default=None, ge=1, le=10, description="Voice tuning variation (1-10)"
    )


class TTSResponse(BaseModel):
    id: str
    filename: str
    voice: str
    mode: str
    preset: str
    duration: Optional[float] = None
    word_count: int
    status: str = "completed"
    captions: Optional[list[dict]] = None


class PreviewResponse(BaseModel):
    id: str
    filename: str
    voice: str
    mode: str
