from sqlalchemy import Column, String, Float, Integer, DateTime, Text, Boolean, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from .database import Base


class Project(Base):
    __tablename__ = "projects"

    id = Column(String, primary_key=True, index=True)
    name = Column(String, nullable=False)
    title = Column(String, nullable=True)
    script_text = Column(Text, nullable=True)
    status = Column(String, nullable=False, default="draft")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    render_jobs = relationship("RenderJob", back_populates="project", cascade="all, delete-orphan")
    generated_audios = relationship("GeneratedAudio", back_populates="project", cascade="all, delete-orphan")


class GeneratedAudio(Base):
    __tablename__ = "generated_audio"

    id = Column(String, primary_key=True, index=True)
    project_id = Column(String, ForeignKey("projects.id"), nullable=True, index=True)
    filename = Column(String, nullable=False, unique=True, index=True)
    voice = Column(String, nullable=False, index=True)
    mode = Column(String, nullable=False)
    preset = Column(String, nullable=False, default="storytelling")
    text = Column(Text, nullable=False)
    word_count = Column(Integer, nullable=False)
    duration = Column(Float, nullable=True)
    speed = Column(Float, nullable=True)
    tone = Column(String, nullable=True)
    file_size = Column(Integer, nullable=True)
    status = Column(String, nullable=False, default="ready")
    captions_json = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    project = relationship("Project", back_populates="generated_audios")


class VideoAsset(Base):
    __tablename__ = "video_assets"

    id = Column(String, primary_key=True, index=True)
    filename = Column(String, nullable=False, unique=True, index=True)
    original_name = Column(String, nullable=True)
    storage_key = Column(String, nullable=False)
    duration = Column(Float, nullable=True)
    width = Column(Integer, nullable=True)
    height = Column(Integer, nullable=True)
    fps = Column(Float, nullable=True)
    codec = Column(String, nullable=True)
    file_size = Column(Integer, nullable=True)
    tags = Column(Text, nullable=True)
    category = Column(String, nullable=True, index=True)
    folder = Column(String, nullable=True, index=True)  # source folder: SandTagious, odlysatisfy, etc.
    usage_count = Column(Integer, nullable=False, default=0)
    last_used_at = Column(DateTime(timezone=True), nullable=True)
    status = Column(String, nullable=False, default="ready")
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class RenderJob(Base):
    __tablename__ = "render_jobs"

    id = Column(String, primary_key=True, index=True)
    project_id = Column(String, ForeignKey("projects.id"), nullable=False, index=True)
    generated_audio_id = Column(String, ForeignKey("generated_audio.id"), nullable=True)
    status = Column(String, nullable=False, default="queued")
    progress = Column(Integer, nullable=False, default=0)
    current_stage = Column(String, nullable=True)
    error_code = Column(String, nullable=True)
    error_message = Column(Text, nullable=True)
    render_seed = Column(Integer, nullable=True)
    selected_asset_ids = Column(Text, nullable=True)
    video_folder = Column(String, nullable=True)
    target_duration = Column(Float, nullable=True)
    caption_data = Column(Text, nullable=True)
    timeline_data = Column(Text, nullable=True)
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    project = relationship("Project", back_populates="render_jobs")
    audio = relationship("GeneratedAudio", foreign_keys=[generated_audio_id])
    output = relationship("RenderOutput", back_populates="render_job", uselist=False)


class RenderOutput(Base):
    __tablename__ = "render_outputs"

    id = Column(String, primary_key=True, index=True)
    render_job_id = Column(String, ForeignKey("render_jobs.id"), nullable=False, unique=True)
    video_filename = Column(String, nullable=True)
    thumbnail_filename = Column(String, nullable=True)
    duration = Column(Float, nullable=True)
    width = Column(Integer, nullable=True)
    height = Column(Integer, nullable=True)
    file_size = Column(Integer, nullable=True)
    codec = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    render_job = relationship("RenderJob", back_populates="output")


class Niche(Base):
    __tablename__ = "niches"

    id = Column(String, primary_key=True, index=True)
    name = Column(String, nullable=False, unique=True)
    display_name = Column(String, nullable=False)
    keywords = Column(Text, nullable=True)  # JSON list
    audience_age_min = Column(Integer, nullable=True)
    audience_age_max = Column(Integer, nullable=True)
    audience_interests = Column(Text, nullable=True)  # JSON list
    hook_style = Column(String, nullable=True)
    optimal_duration_min = Column(Integer, nullable=True)
    optimal_duration_max = Column(Integer, nullable=True)
    voice_preference = Column(String, nullable=True)
    tone_preference = Column(String, nullable=True)
    preset_preference = Column(String, nullable=True)
    description = Column(Text, nullable=True)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    topics = relationship("Topic", back_populates="niche", cascade="all, delete-orphan")


class Topic(Base):
    __tablename__ = "topics"

    id = Column(String, primary_key=True, index=True)
    niche_id = Column(String, ForeignKey("niches.id"), nullable=False, index=True)
    title = Column(String, nullable=False)
    subtopics = Column(Text, nullable=True)  # JSON list
    trend_score = Column(Float, nullable=True, default=0.5)
    competition_score = Column(Float, nullable=True, default=0.3)
    evergreen = Column(Boolean, nullable=False, default=True)
    related_topics = Column(Text, nullable=True)  # JSON list
    estimated_ctr = Column(Float, nullable=True, default=0.04)
    times_used = Column(Integer, nullable=False, default=0)
    last_used_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    niche = relationship("Niche", back_populates="topics")


class GeneratedScript(Base):
    __tablename__ = "generated_scripts"

    id = Column(String, primary_key=True, index=True)
    batch_id = Column(String, ForeignKey("batch_jobs.id"), nullable=True, index=True)
    topic_id = Column(String, ForeignKey("topics.id"), nullable=True, index=True)
    niche = Column(String, nullable=True, index=True)
    script_type = Column(String, nullable=False)
    hook = Column(Text, nullable=True)
    body = Column(Text, nullable=True)
    close = Column(Text, nullable=True)
    full_text = Column(Text, nullable=False)
    word_count = Column(Integer, nullable=False)
    estimated_duration = Column(Float, nullable=True)
    target_emotion = Column(String, nullable=True)
    retention_tactics = Column(Text, nullable=True)  # JSON list
    quality_score = Column(Float, nullable=True)
    status = Column(String, nullable=False, default="pending")
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    batch = relationship("BatchJob", back_populates="scripts")
    topic = relationship("Topic")


class BatchJob(Base):
    __tablename__ = "batch_jobs"

    id = Column(String, primary_key=True, index=True)
    name = Column(String, nullable=False)
    config = Column(Text, nullable=True)  # JSON config
    status = Column(String, nullable=False, default="pending")
    total_items = Column(Integer, nullable=False, default=0)
    completed_items = Column(Integer, nullable=False, default=0)
    failed_items = Column(Integer, nullable=False, default=0)
    error_log = Column(Text, nullable=True)  # JSON list
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)

    scripts = relationship("GeneratedScript", back_populates="batch", cascade="all, delete-orphan")


class ContentCalendar(Base):
    __tablename__ = "content_calendar"

    id = Column(String, primary_key=True, index=True)
    scheduled_date = Column(String, nullable=False, index=True)
    scheduled_time = Column(String, nullable=True)
    niche_id = Column(String, ForeignKey("niches.id"), nullable=True, index=True)
    topic_id = Column(String, ForeignKey("topics.id"), nullable=True)
    script_id = Column(String, ForeignKey("generated_scripts.id"), nullable=True)
    render_output_id = Column(String, ForeignKey("render_outputs.id"), nullable=True)
    status = Column(String, nullable=False, default="queued")
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class VideoAnalytics(Base):
    __tablename__ = "video_analytics"

    id = Column(String, primary_key=True, index=True)
    render_output_id = Column(String, ForeignKey("render_outputs.id"), nullable=True, index=True)
    script_id = Column(String, ForeignKey("generated_scripts.id"), nullable=True)
    topic_id = Column(String, ForeignKey("topics.id"), nullable=True)
    views = Column(Integer, nullable=False, default=0)
    watch_time_seconds = Column(Float, nullable=True, default=0)
    retention_curve = Column(Text, nullable=True)  # JSON
    likes = Column(Integer, nullable=False, default=0)
    comments = Column(Integer, nullable=False, default=0)
    shares = Column(Integer, nullable=False, default=0)
    performance_score = Column(Float, nullable=True)
    measured_at = Column(DateTime(timezone=True), server_default=func.now())


class YouTubeCredential(Base):
    __tablename__ = "youtube_credentials"

    id = Column(String, primary_key=True, index=True)
    channel_id = Column(String, nullable=True)
    channel_title = Column(String, nullable=True)
    access_token = Column(Text, nullable=False)
    refresh_token = Column(Text, nullable=False)
    token_expiry = Column(DateTime(timezone=True), nullable=False)
    client_id = Column(String, nullable=False)
    client_secret = Column(String, nullable=False)
    scopes = Column(Text, nullable=False)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


class YouTubeUpload(Base):
    __tablename__ = "youtube_uploads"

    id = Column(String, primary_key=True, index=True)
    render_output_id = Column(String, ForeignKey("render_outputs.id"), nullable=False, index=True)
    video_id = Column(String, nullable=True)
    video_url = Column(String, nullable=True)
    title = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    tags = Column(Text, nullable=True)  # JSON list
    thumbnail_path = Column(String, nullable=True)
    privacy_status = Column(String, nullable=False, default="public")
    playlist_id = Column(String, nullable=True)
    scheduled_time = Column(DateTime(timezone=True), nullable=True)
    status = Column(String, nullable=False, default="pending")
    error_message = Column(Text, nullable=True)
    youtube_views = Column(Integer, nullable=True)
    youtube_likes = Column(Integer, nullable=True)
    youtube_comments = Column(Integer, nullable=True)
    last_analytics_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    uploaded_at = Column(DateTime(timezone=True), nullable=True)

    render_output = relationship("RenderOutput")


class UsedTheme(Base):
    __tablename__ = "used_themes"

    id = Column(String, primary_key=True, index=True)
    theme = Column(Text, nullable=False, unique=True, index=True)
    session_id = Column(String, nullable=True)
    quality_score = Column(Float, nullable=True)
    category = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class Template(Base):
    __tablename__ = "templates"

    id = Column(String, primary_key=True, index=True)
    name = Column(String, nullable=False)
    version = Column(Integer, nullable=False, default=1)
    description = Column(Text, nullable=True)
    aspect_ratio = Column(String, nullable=False, default="9:16")
    resolution_width = Column(Integer, nullable=False, default=1080)
    resolution_height = Column(Integer, nullable=False, default=1920)
    fps = Column(Integer, nullable=False, default=30)
    config = Column(Text, nullable=False)  # JSON config
    is_default = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
