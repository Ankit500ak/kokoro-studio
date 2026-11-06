from pydantic_settings import BaseSettings
from pathlib import Path
from typing import List


class Settings(BaseSettings):
    # Resolve the backend .env from this file, so startup works from any cwd.
    model_config = {
        "env_file": Path(__file__).resolve().parents[2] / ".env",
        "env_file_encoding": "utf-8",
    }

    APP_NAME: str = "Kokoro Studio"
    APP_VERSION: str = "1.0.0"
    HOST: str = "0.0.0.0"
    PORT: int = 8000

    STORAGE_DIR: Path = Path(__file__).parent.parent / "storage"
    AUDIO_DIR: Path = STORAGE_DIR / "audio"
    PREVIEWS_DIR: Path = STORAGE_DIR / "previews"
    MEDIA_DIR: Path = STORAGE_DIR / "media"
    RENDER_DIR: Path = STORAGE_DIR / "renders"
    TUNING_DIR: Path = STORAGE_DIR / "tuning"
    FORGE_THUMBS_DIR: Path = STORAGE_DIR / "forge_thumbs"

    DEFAULT_VOICE: str = "am_adam"
    DEFAULT_SPEED: float = 1.0
    SAMPLE_RATE: int = 24000

    MAX_TEXT_LENGTH: int = 10000
    MIN_SPEED: float = 0.5
    MAX_SPEED: float = 1.3

    MAX_UPLOAD_SIZE: int = 500 * 1024 * 1024  # 500MB

    # TTS generation timeouts (seconds)
    # CPU synthesis with multi-pass + enhancement measures ~0.7-1.0 s/word
    # (horror preset is slower); budgets must cover a full 400-word chunk.
    TTS_CHUNK_SIZE: int = 400  # Max words per chunk for long scripts
    TTS_CHUNK_TIMEOUT_BASE: float = 180.0  # Base timeout per chunk (seconds)
    TTS_CHUNK_TIMEOUT_PER_WORD: float = 1.2  # Extra seconds per word in chunk
    TTS_SINGLE_TIMEOUT_BASE: float = 300.0  # Base timeout for single-pass
    TTS_SINGLE_TIMEOUT_PER_WORD: float = 1.0  # Extra seconds per word (single)
    TTS_PREVIEW_TIMEOUT: float = 60.0

    # Render duration cap (seconds). Legacy Shorts renders stay capped at 119s;
    # long-form jobs pass target_duration (60-600) to lift the cap.
    RENDER_DEFAULT_MAX_DURATION: float = 119.0
    RENDER_MAX_DURATION: float = 600.0
    # Keep long renders under Telegram's ~50MB bot upload limit.
    RENDER_TELEGRAM_MAX_MB: float = 45.0
    STORY_PIPELINE_TIMEOUT: float = 1800.0
    # Long-form (8-min) stories need bigger single-stage budgets: the unified
    # polish stage rewrites the full script and can retry once on AI failure.
    STORY_STAGE_TIMEOUT: float = 360.0
    STORY_ENABLE_ENHANCEMENT: bool = False
    # Stage 12: titles / description / tags / audience / thumbnail pack.
    STORY_ENABLE_PUBLISH_PACK: bool = True

    YOUTUBE_CLIENT_ID: str = ""
    YOUTUBE_CLIENT_SECRET: str = ""
    YOUTUBE_REDIRECT_URI: str = "http://localhost:8000/api/youtube/callback"
    YOUTUBE_SCOPES: str = "https://www.googleapis.com/auth/youtube.upload https://www.googleapis.com/auth/youtube https://www.googleapis.com/auth/youtube.force-ssl"

    # YouTube auto-upload (opt-in): when a render finishes, upload it without
    # a manual POST /api/youtube/upload. OFF by default; uploads start out
    # private so a human can review before anything goes public.
    AUTO_UPLOAD_YOUTUBE: bool = False
    UPLOAD_PRIVACY_STATUS: str = "private"
    UPLOAD_CATEGORY_ID: str = "22"
    UPLOAD_TAGS: str = ""  # comma-separated extra tags merged into every auto-upload
    UPLOAD_NOTIFY_TELEGRAM: bool = True

    CORS_ORIGINS: List[str] = ["*"]

    # Encryption key for sensitive data (YouTube tokens) - Fernet format
    ENCRYPTION_KEY: str = ""

    # Gemini API - the sole AI provider (StoryForge, metadata generation,
    # /api/tts think-refine). Get a key at https://aistudio.google.com/apikey
    # and set GEMINI_API_KEY in .env. Calls use Google AI Studio's
    # OpenAI-compatible endpoint, hence the /v1beta/openai base URL.
    GEMINI_API_KEY: str = ""
    GEMINI_BASE_URL: str = "https://generativelanguage.googleapis.com/v1beta/openai"
    GEMINI_MODEL: str = "gemini-3.8-flash"
    GEMINI_TIMEOUT: float = 60.0
    GEMINI_MAX_TOKENS: int = 4096
    GEMINI_TEMPERATURE: float = 0.8

    # Telegram Auto-Pilot (keep secrets in .env, not in .bat launchers)
    TELEGRAM_BOT_TOKEN: str = ""
    TELEGRAM_CHAT_ID: str = ""


settings = Settings()
settings.AUDIO_DIR.mkdir(parents=True, exist_ok=True)
settings.PREVIEWS_DIR.mkdir(parents=True, exist_ok=True)
settings.MEDIA_DIR.mkdir(parents=True, exist_ok=True)
settings.RENDER_DIR.mkdir(parents=True, exist_ok=True)
settings.TUNING_DIR.mkdir(parents=True, exist_ok=True)
settings.FORGE_THUMBS_DIR.mkdir(parents=True, exist_ok=True)
