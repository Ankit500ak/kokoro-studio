# YouTube Auto-Upload Architecture

## System Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           ORCHESTRATOR LAYER                                │
│  Upload queue, scheduling, retry, status tracking, error recovery          │
├─────────────────────────────────────────────────────────────────────────────┤
│                         METADATA GENERATOR                                  │
│  Title, description, tags, hashtags — all SEO-optimized via LLM            │
├─────────────────────────────────────────────────────────────────────────────┤
│                         THUMBNAIL ENGINE                                    │
│  Multi-layer compositing: background + text overlay + branding              │
├─────────────────────────────────────────────────────────────────────────────┤
│                         YOUTUBE CLIENT                                      │
│  OAuth2 token management, resumable uploads, API rate limiting             │
├─────────────────────────────────────────────────────────────────────────────┤
│                         ANALYTICS FEEDBACK                                  │
│  Performance tracking → strategy updates → better future uploads           │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Layer 1: YouTube OAuth2 Client

### Authentication Flow

```
One-time Setup:
  1. User visits /api/youtube/auth → generates Google OAuth URL
  2. User authorizes in browser → redirected to /api/youtube/callback
  3. Backend exchanges code for refresh_token → stores encrypted in DB
  4. All future uploads use stored refresh_token automatically

Runtime (zero intervention):
  1. Check if access_token is expired
  2. If expired → use refresh_token to get new access_token
  3. Use access_token for YouTube Data API v3 calls
```

### Token Storage

```python
# backend/app/core/models.py — new table
class YouTubeCredential(Base):
    __tablename__ = "youtube_credentials"

    id = Column(String, primary_key=True)           # "default" or channel ID
    channel_id = Column(String, nullable=True)
    channel_title = Column(String, nullable=True)
    access_token = Column(Text, nullable=False)      # encrypted
    refresh_token = Column(Text, nullable=False)     # encrypted
    token_expiry = Column(DateTime, nullable=False)
    client_id = Column(String, nullable=False)
    client_secret = Column(String, nullable=False)
    scopes = Column(Text, nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
```

### YouTube API Client

```python
# backend/app/services/youtube_client.py

import httpx
from datetime import datetime, timedelta

YOUTUBE_API_BASE = "https://www.googleapis.com/youtube/v3"
YOUTUBE_UPLOAD_URL = "https://www.googleapis.com/upload/youtube/v3/videos"

class YouTubeClient:
    def __init__(self, credential: YouTubeCredential):
        self.credential = credential
        self._access_token = credential.access_token
        self._token_expiry = credential.token_expiry

    async def _refresh_token_if_needed(self):
        if datetime.utcnow() >= self._token_expiry - timedelta(minutes=5):
            async with httpx.AsyncClient() as client:
                resp = await client.post("https://oauth2.googleapis.com/token", data={
                    "client_id": self.credential.client_id,
                    "client_secret": self.credential.client_secret,
                    "refresh_token": self.credential.refresh_token,
                    "grant_type": "refresh_token",
                })
                token_data = resp.json()
                self._access_token = token_data["access_token"]
                self._token_expiry = datetime.utcnow() + timedelta(seconds=token_data["expires_in"])
                # Persist new token to DB
                self.credential.access_token = self._access_token
                self.credential.token_expiry = self._token_expiry

    async def upload_video(
        self,
        video_path: str,
        title: str,
        description: str,
        tags: list[str],
        category_id: str = "28",        # Science & Technology
        privacy_status: str = "public", # public, unlisted, private
        thumbnail_path: str | None = None,
        playlist_id: str | None = None,
        schedule_time: datetime | None = None,
    ) -> dict:
        await self._refresh_token_if_needed()

        # Step 1: Initialize resumable upload
        metadata = {
            "snippet": {
                "title": title[:100],          # max 100 chars
                "description": description[:5000],  # max 5000 chars
                "tags": tags[:500],             # max 500 tags, 5000 chars total
                "categoryId": category_id,
                "defaultLanguage": "en",
                "defaultAudioLanguage": "en",
            },
            "status": {
                "privacyStatus": privacy_status,
                "selfDeclaredMadeForKids": False,
                "embeddable": True,
                "publicStatsViewable": True,
            },
        }

        if schedule_time and privacy_status == "private":
            metadata["status"]["privacyStatus"] = "private"
            metadata["status"]["publishAt"] = schedule_time.isoformat() + "Z"

        if playlist_id:
            metadata["snippet"]["playlistId"] = playlist_id

        async with httpx.AsyncClient(timeout=300) as client:
            # Initialize resumable upload session
            init_resp = await client.post(
                f"{YOUTUBE_UPLOAD_URL}?uploadType=resumable&part=snippet,status",
                headers={
                    "Authorization": f"Bearer {self._access_token}",
                    "Content-Type": "application/json",
                    "X-Upload-Content-Type": "video/mp4",
                    "X-Upload-Content-Length": str(os.path.getsize(video_path)),
                },
                json=metadata,
            )

            upload_url = init_resp.headers.get("Location")
            if not upload_url:
                raise YouTubeUploadError(f"Init failed: {init_resp.text}")

            # Step 2: Upload video file in chunks
            file_size = os.path.getsize(video_path)
            chunk_size = 10 * 1024 * 1024  # 10MB chunks

            with open(video_path, "rb") as f:
                offset = 0
                while offset < file_size:
                    chunk = f.read(chunk_size)
                    chunk_end = offset + len(chunk) - 1

                    resp = await client.put(
                        upload_url,
                        content=chunk,
                        headers={
                            "Content-Length": str(len(chunk)),
                            "Content-Range": f"bytes {offset}-{chunk_end}/{file_size}",
                        },
                    )

                    if resp.status_code in (200, 201):
                        video_id = resp.json()["id"]
                        break
                    elif resp.status_code == 308:
                        offset += len(chunk)
                    else:
                        raise YouTubeUploadError(f"Upload chunk failed: {resp.text}")

            # Step 3: Set thumbnail if provided
            if thumbnail_path and os.path.exists(thumbnail_path):
                await self._set_thumbnail(video_id, thumbnail_path)

            return {"video_id": video_id, "url": f"https://youtube.com/watch?v={video_id}"}

    async def _set_thumbnail(self, video_id: str, thumbnail_path: str):
        await self._refresh_token_if_needed()
        async with httpx.AsyncClient(timeout=60) as client:
            with open(thumbnail_path, "rb") as f:
                resp = await client.post(
                    f"{YOUTUBE_API_BASE}/thumbnails/set?videoId={video_id}",
                    headers={"Authorization": f"Bearer {self._access_token}"},
                    files={"media": ("thumbnail.jpg", f, "image/jpeg")},
                )
            if resp.status_code not in (200, 201):
                log.warning(f"Thumbnail upload failed: {resp.text}")

    async def get_upload_stats(self, video_id: str) -> dict:
        await self._refresh_token_if_needed()
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{YOUTUBE_API_BASE}/videos?part=statistics&id={video_id}",
                headers={"Authorization": f"Bearer {self._access_token}"},
            )
            items = resp.json().get("items", [])
            if items:
                return items[0].get("statistics", {})
            return {}

    async def list_playlists(self) -> list[dict]:
        await self._refresh_token_if_needed()
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{YOUTUBE_API_BASE}/playlists?part=snippet&mine=true&maxResults=50",
                headers={"Authorization": f"Bearer {self._access_token}"},
            )
            return resp.json().get("items", [])
```

---

## Layer 2: Thumbnail Engine

### Architecture

```
┌─────────────────────────────────────────────────┐
│                 Thumbnail Pipeline               │
├─────────────────────────────────────────────────┤
│  1. Background Selection                         │
│     └─ Extract frame from video OR use solid     │
│  2. Overlay Generation                          │
│     └─ Title text with word wrap + shadow        │
│  3. Branding                                    │
│     └─ Channel logo/watermark in corner          │
│  4. Effects                                     │
│     └─ Vignette, brightness boost, blur edges    │
│  5. Export                                      │
│     └─ 1280x720 JPEG (YouTube optimal)           │
└─────────────────────────────────────────────────┘
```

### Thumbnail Design System

```python
# backend/app/services/thumbnail_engine.py

THUMBNAIL_CONFIGS = {
    "true_crime": {
        "bg_filter": "darken",
        "title_color": "#FF4444",
        "title_position": "center",
        "font_size": 64,
        "font_weight": "black",
        "shadow_color": "#000000",
        "shadow_offset": 4,
        "vignette_strength": 0.6,
        "accent_color": "#FF0000",
        "style": "dramatic",
    },
    "psychology": {
        "bg_filter": "cool",
        "title_color": "#FFFFFF",
        "title_position": "center",
        "font_size": 56,
        "font_weight": "bold",
        "shadow_color": "#1a1a2e",
        "shadow_offset": 3,
        "vignette_strength": 0.4,
        "accent_color": "#9b59b6",
        "style": "clean",
    },
    "tech_tips": {
        "bg_filter": "saturate",
        "title_color": "#00D4FF",
        "title_position": "center",
        "font_size": 52,
        "font_weight": "bold",
        "shadow_color": "#0a0a0a",
        "shadow_offset": 3,
        "vignette_strength": 0.3,
        "accent_color": "#00D4FF",
        "style": "modern",
    },
    "finance": {
        "bg_filter": "warm",
        "title_color": "#00FF88",
        "title_position": "center",
        "font_size": 58,
        "font_weight": "black",
        "shadow_color": "#0a1a0a",
        "shadow_offset": 4,
        "vignette_strength": 0.5,
        "accent_color": "#00FF88",
        "style": "bold",
    },
    "science": {
        "bg_filter": "cool",
        "title_color": "#FFFFFF",
        "title_position": "center",
        "font_size": 54,
        "font_weight": "bold",
        "shadow_color": "#0a0a2e",
        "shadow_offset": 3,
        "vignette_strength": 0.4,
        "accent_color": "#3498db",
        "style": "cinematic",
    },
    "history": {
        "bg_filter": "sepia",
        "title_color": "#F4D03F",
        "title_position": "center",
        "font_size": 56,
        "font_weight": "black",
        "shadow_color": "#2c1810",
        "shadow_offset": 4,
        "vignette_strength": 0.7,
        "accent_color": "#F4D03F",
        "style": "vintage",
    },
    "motivation": {
        "bg_filter": "high_contrast",
        "title_color": "#FFFFFF",
        "title_position": "center",
        "font_size": 60,
        "font_weight": "black",
        "shadow_color": "#000000",
        "shadow_offset": 5,
        "vignette_strength": 0.3,
        "accent_color": "#FF6B00",
        "style": "intense",
    },
    "horror": {
        "bg_filter": "darken",
        "title_color": "#CC0000",
        "title_position": "center",
        "font_size": 58,
        "font_weight": "black",
        "shadow_color": "#000000",
        "shadow_offset": 5,
        "vignette_strength": 0.8,
        "accent_color": "#CC0000",
        "style": "horror",
    },
    "philosophy": {
        "bg_filter": "muted",
        "title_color": "#ECF0F1",
        "title_position": "center",
        "font_size": 52,
        "font_weight": "bold",
        "shadow_color": "#1a1a2e",
        "shadow_offset": 3,
        "vignette_strength": 0.5,
        "accent_color": "#8e44ad",
        "style": "minimal",
    },
    "nature": {
        "bg_filter": "saturate",
        "title_color": "#FFFFFF",
        "title_position": "center",
        "font_size": 56,
        "font_weight": "bold",
        "shadow_color": "#0a1a0a",
        "shadow_offset": 3,
        "vignette_strength": 0.3,
        "accent_color": "#27ae60",
        "style": "natural",
    },
}


class ThumbnailEngine:
    """Generate professional YouTube thumbnails using Pillow + FFmpeg."""

    def __init__(self):
        self.output_size = (1280, 720)  # YouTube optimal

    def generate(
        self,
        video_path: str,
        title: str,
        niche: str,
        output_path: str,
        subtitle: str | None = None,
    ) -> str:
        """
        Generate a thumbnail from video frame + text overlay.
        Returns the output path.
        """
        config = THUMBNAIL_CONFIGS.get(niche, THUMBNAIL_CONFIGS["psychology"])

        # Step 1: Extract best frame from video
        frame = self._extract_best_frame(video_path)

        # Step 2: Apply visual effects
        frame = self._apply_filter(frame, config["bg_filter"])
        frame = self._apply_vignette(frame, config["vignette_strength"])

        # Step 3: Render title text with wrapping
        frame = self._render_title(frame, title, config)

        # Step 4: Render subtitle if provided
        if subtitle:
            frame = self._render_subtitle(frame, subtitle, config)

        # Step 5: Add accent bar / visual element
        frame = self._add_accent_element(frame, config)

        # Step 6: Save
        frame.save(output_path, "JPEG", quality=92)
        return output_path

    def _extract_best_frame(self, video_path: str) -> Image:
        """Extract frame at 25% mark (usually good composition)."""
        # Use FFmpeg to extract frame at 25% of duration
        duration = self._get_video_duration(video_path)
        target_time = duration * 0.25

        cmd = [
            "ffmpeg", "-y",
            "-i", video_path,
            "-ss", str(target_time),
            "-vframes", "1",
            "-vf", f"scale={self.output_size[0]}:{self.output_size[1]}:force_original_aspect_ratio=increase,crop={self.output_size[0]}:{self.output_size[1]}",
            "-q:v", "2",
            "/tmp/frame_capture.jpg"
        ]
        subprocess.run(cmd, capture_output=True, timeout=30)
        return Image.open("/tmp/frame_capture.jpg").convert("RGB")

    def _apply_filter(self, img: Image, filter_name: str) -> Image:
        """Apply visual filter to background."""
        from PIL import ImageEnhance, ImageFilter

        if filter_name == "darken":
            enhancer = ImageEnhance.Brightness(img)
            img = enhancer.enhance(0.6)
        elif filter_name == "saturate":
            enhancer = ImageEnhance.Color(img)
            img = enhancer.enhance(1.4)
        elif filter_name == "cool":
            img = ImageEnhance.Color(img).enhance(0.8)
            # Slight blue tint via channel manipulation
        elif filter_name == "warm":
            img = ImageEnhance.Color(img).enhance(1.1)
        elif filter_name == "sepia":
            img = ImageEnhance.Color(img).enhance(0.3)
            enhancer = ImageEnhance.Brightness(img)
            img = enhancer.enhance(1.1)
        elif filter_name == "high_contrast":
            enhancer = ImageEnhance.Contrast(img)
            img = enhancer.enhance(1.5)
            img = ImageEnhance.Brightness(img).enhance(0.8)
        elif filter_name == "muted":
            img = ImageEnhance.Color(img).enhance(0.5)
            img = ImageEnhance.Brightness(img).enhance(0.9)
        return img

    def _apply_vignette(self, img: Image, strength: float) -> Image:
        """Apply vignette effect (darkened edges)."""
        vignette = Image.new("RGB", img.size, (0, 0, 0))
        # Radial gradient mask
        mask = Image.new("L", img.size, 0)
        draw = ImageDraw.Draw(mask)
        cx, cy = img.size[0] // 2, img.size[1] // 2
        max_r = math.sqrt(cx**2 + cy**2)
        for r in range(int(max_r), 0, -2):
            opacity = int(255 * (1 - (r / max_r)) * strength)
            draw.ellipse([cx-r, cy-r, cx+r, cy+r], fill=opacity)
        return Image.composite(img, vignette, mask)

    def _render_title(self, img: Image, title: str, config: dict) -> Image:
        """Render title text with word wrap, shadow, and positioning."""
        from PIL import ImageDraw, ImageFont

        draw = ImageDraw.Draw(img)
        font_size = config["font_size"]

        # Load font (try system fonts, fallback to default)
        try:
            font = ImageFont.truetype("arialbd.ttf", font_size)
        except OSError:
            try:
                font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", font_size)
            except OSError:
                font = ImageFont.load_default()

        # Word wrap title
        wrapped = self._word_wrap(draw, title.upper(), font, self.output_size[0] - 120)

        # Calculate total text height
        bbox = draw.multiline_textbbox((0, 0), wrapped, font=font)
        text_height = bbox[3] - bbox[1]
        text_width = bbox[2] - bbox[0]

        # Center position
        x = (self.output_size[0] - text_width) // 2
        y = (self.output_size[1] - text_height) // 2

        # Draw shadow
        shadow_offset = config["shadow_offset"]
        shadow_color = config["shadow_color"]
        for dx in range(-shadow_offset, shadow_offset + 1):
            for dy in range(-shadow_offset, shadow_offset + 1):
                if dx != 0 or dy != 0:
                    draw.multiline_text(
                        (x + dx, y + dy), wrapped,
                        font=font, fill=shadow_color,
                        align="center", spacing=8
                    )

        # Draw main text
        draw.multiline_text(
            (x, y), wrapped,
            font=font, fill=config["title_color"],
            align="center", spacing=8
        )

        return img

    def _word_wrap(self, draw, text: str, font, max_width: int) -> str:
        """Wrap text to fit within max_width."""
        words = text.split()
        lines = []
        current_line = ""

        for word in words:
            test_line = f"{current_line} {word}".strip()
            bbox = draw.textbbox((0, 0), test_line, font=font)
            if bbox[2] - bbox[0] <= max_width:
                current_line = test_line
            else:
                if current_line:
                    lines.append(current_line)
                current_line = word

        if current_line:
            lines.append(current_line)

        return "\n".join(lines[:3])  # max 3 lines

    def _add_accent_element(self, img: Image, config: dict) -> Image:
        """Add accent bar or visual element."""
        from PIL import ImageDraw

        draw = ImageDraw.Draw(img)
        accent = config["accent_color"]

        # Bottom accent bar
        bar_height = 6
        draw.rectangle(
            [0, self.output_size[1] - bar_height, self.output_size[0], self.output_size[1]],
            fill=accent
        )

        # Side accent line
        draw.rectangle(
            [0, 0, 4, self.output_size[1]],
            fill=accent
        )

        return img
```

### Thumbnail Styles per Niche

| Niche | Background | Title Color | Accent | Effect |
|-------|-----------|-------------|--------|--------|
| true_crime | Dark frame | Red | Red bar | Dramatic vignette |
| psychology | Cool frame | White | Purple | Clean, minimal |
| tech_tips | Saturated | Cyan | Cyan | Modern, sharp |
| finance | Warm frame | Green | Green | Bold, confident |
| science | Cool frame | White | Blue | Cinematic |
| history | Sepia frame | Gold | Gold | Vintage |
| motivation | High contrast | White | Orange | Intense |
| horror | Dark frame | Dark Red | Red | Heavy vignette |
| philosophy | Muted frame | Light | Purple | Minimal |
| nature | Saturated | White | Green | Natural |

---

## Layer 3: Metadata Generator (SEO Optimized)

### Title Generation

```python
# backend/app/services/metadata_generator.py

TITLE_PATTERNS = {
    "true_crime": [
        "The {topic} That Nobody Talks About",
        "What They Found About {topic} Changed Everything",
        "{topic}: The Story They Don't Want You to Know",
        "This {topic} Will Keep You Up at Night",
        "The Dark Truth Behind {topic}",
    ],
    "psychology": [
        "Why {topic} Is More Common Than You Think",
        "The Science Behind {topic} (It's Fascinating)",
        "{topic} — The Truth Nobody Tells You",
        "If You Do This, You Might Be {topic}",
        "Your Brain Does {topic} and You Don't Even Know",
    ],
    "tech_tips": [
        "This {topic} Hack Will Save You Hours",
        "Nobody Talks About This {topic} Trick",
        "{topic}: The Feature Apple/Google Doesn't Advertise",
        "Stop Doing This Wrong — {topic} Explained",
        "I Can't Believe {topic} Was This Easy",
    ],
    "finance": [
        "How to {topic} (Step by Step)",
        "The {topic} Mistake That Keeps You Broke",
        "{topic} Changed My Life — Here's How",
        "Why Rich People Never {topic}",
        "The Secret to {topic} Nobody Teaches You",
    ],
    "science": [
        "What Happens When {topic}? The Answer Is Terrifying",
        "{topic}: The Discovery That Breaks Physics",
        "Nobody Expected What Happened With {topic}",
        "The Mind-Blowing Truth About {topic}",
        "{topic} Is Way More Complex Than You Think",
    ],
    "history": [
        "The {topic} That Changed the World Forever",
        "What They Found About {topic} Shocked Everyone",
        "{topic}: The Untold Story",
        "This {topic} Was Hidden for Centuries",
        "The {topic} Nobody Dares to Talk About",
    ],
    "motivation": [
        "This {topic} Habit Will Change Your Life",
        "The {topic} Rule That Separates Winners from Losers",
        "Why {topic} Is the Key to Everything",
        "Do This Every Morning — {topic} Explained",
        "The {topic} Mindset Nobody Teaches You",
    ],
    "horror": [
        "Don't Watch This at Night — {topic}",
        "The {topic} That Haunts Me to This Day",
        "{topic}: This Actually Happened",
        "I Regret Learning About {topic}",
        "The {topic} Nobody Survives",
    ],
    "philosophy": [
        "The {topic} Paradox That Breaks Your Brain",
        "What {topic} Really Means (Deep Answer)",
        "{topic} — The Question Philosophy Can't Answer",
        "If You Understand {topic}, You Understand Life",
        "The {topic} Thought Experiment That Changes Everything",
    ],
    "nature": [
        "The {topic} That Defies All Logic",
        "Nobody Can Explain Why {topic}",
        "{topic}: Nature's Most Incredible Secret",
        "This {topic} Fact Will Blow Your Mind",
        "The {topic} Nobody Expected to Exist",
    ],
}
```

### Description Template

```python
DESCRIPTION_TEMPLATE = """{hook_line}

{body_paragraph}

{timestamps}

{hashtags}

{cta}

---
{channel_boilerplate}"""

TIMESTAMPS_TEMPLATE = """
Timestamps:
{timestamps_list}
"""

HASHTAGS_TEMPLATE = "#{niche} {topic_hashtags} #shorts #viral #facts"

BOILERPLATE = """
 subscribe for more {niche} content!
"""

CTA_OPTIONS = [
    "Like & Subscribe for more!",
    "Follow for daily content!",
    "Drop a comment if you agree!",
    "Share this with someone who needs to hear this!",
]
```

### Tag Generator

```python
class TagGenerator:
    """Generate YouTube tags optimized for search discovery."""

    NICHE_BASE_TAGS = {
        "true_crime": ["true crime", "crime documentary", "unsolved mystery", "detective", "cold case", "forensic", "crime story", "mystery"],
        "psychology": ["psychology", "mental health", "brain", "human behavior", "self improvement", "mindset", "narcissist", "emotional intelligence"],
        "tech_tips": ["tech tips", "technology", "AI", "productivity", "life hacks", "smartphone", "computer tips", "gadgets"],
        "finance": ["finance", "money", "investing", "financial freedom", "wealth", "budgeting", "passive income", "stock market"],
        "science": ["science", "space", "physics", "discovery", "NASA", "universe", "experiment", "nature"],
        "history": ["history", "ancient", "civilization", "empire", "war", "historical", "archaeology", "mystery"],
        "motivation": ["motivation", "inspiration", "discipline", "success", "mindset", "self improvement", "habits", "growth"],
        "horror": ["horror", "scary", "creepy", "paranormal", "urban legend", "ghost story", "dark web", "true scary story"],
        "philosophy": ["philosophy", "deep thoughts", "meaning of life", "consciousness", "ethics", "existentialism", "wisdom", "thinking"],
        "nature": ["nature", "animals", "wildlife", "ocean", "species", "ecosystem", "animal facts", "documentary"],
    }

    def generate_tags(
        self,
        title: str,
        niche: str,
        topic: str,
        max_tags: int = 30,
    ) -> list[str]:
        tags = []

        # Base niche tags
        tags.extend(self.NICHE_BASE_TAGS.get(niche, []))

        # Topic-derived tags
        topic_words = topic.lower().split()
        tags.extend(topic_words)

        # Title-derived tags
        title_words = [w.lower() for w in title.split() if len(w) > 3]
        tags.extend(title_words)

        # Deduplicate and clean
        seen = set()
        clean_tags = []
        for tag in tags:
            tag = tag.strip().lower()
            if tag and tag not in seen and len(tag) > 2:
                seen.add(tag)
                clean_tags.append(tag)

        return clean_tags[:max_tags]
```

---

## Layer 4: Upload Orchestrator

### Upload Job Model

```python
# backend/app/core/models.py — new table
class YouTubeUpload(Base):
    __tablename__ = "youtube_uploads"

    id = Column(String, primary_key=True)
    render_output_id = Column(String, ForeignKey("render_outputs.id"), nullable=False)
    video_id = Column(String, nullable=True)       # YouTube video ID
    video_url = Column(String, nullable=True)       # Full YouTube URL
    title = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    tags = Column(Text, nullable=True)              # JSON list
    thumbnail_path = Column(String, nullable=True)
    privacy_status = Column(String, nullable=False, default="public")
    playlist_id = Column(String, nullable=True)
    scheduled_time = Column(DateTime(timezone=True), nullable=True)
    status = Column(String, nullable=False, default="pending")  # pending, uploading, uploaded, failed, scheduled
    error_message = Column(Text, nullable=True)
    youtube_views = Column(Integer, nullable=True)
    youtube_likes = Column(Integer, nullable=True)
    youtube_comments = Column(Integer, nullable=True)
    last_analytics_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    uploaded_at = Column(DateTime(timezone=True), nullable=True)

    render_output = relationship("RenderOutput")
```

### Upload Pipeline

```
Render Output (video + thumbnail)
    │
    ├─► METADATA GENERATION
    │   ├─ LLM generates title (SEO optimized, 60-70 chars)
    │   ├─ LLM generates description (with timestamps, hashtags)
    │   ├─ Tag generator produces 20-30 tags
    │   └─ Hashtag generator produces 5-8 hashtags
    │
    ├─► THUMBNAIL PROCESSING
    │   ├─ Extract best frame from video
    │   ├─ Apply niche-specific visual effects
    │   ├─ Overlay title text with styling
    │   ├─ Add accent elements / branding
    │   └─ Export 1280x720 JPEG
    │
    ├─► VALIDATION
    │   ├─ Title <= 100 chars
    │   ├─ Description <= 5000 chars
    │   ├─ Tags total <= 5000 chars
    │   ├─ Thumbnail is valid JPEG, 1280x720
    │   └─ Video file exists and is valid MP4
    │
    ├─► UPLOAD
    │   ├─ Initialize resumable upload session
    │   ├─ Upload video in 10MB chunks
    │   ├─ Upload custom thumbnail
    │   └─ Confirm upload complete
    │
    └─► POST-UPLOAD
        ├─ Store video_id and URL in DB
        ├─ Optionally add to playlist
        ├─ Schedule if not immediately public
        └─ Log upload for analytics tracking
```

### Upload Queue (Zero Intervention)

```python
# backend/app/services/youtube_uploader.py

class YouTubeUploader:
    def __init__(self):
        self.queue: list[YouTubeUpload] = []
        self.max_concurrent = 3
        self.active_uploads = 0

    async def queue_upload(
        self,
        render_output_id: str,
        auto_metadata: bool = True,
        privacy: str = "public",
        schedule_time: datetime | None = None,
    ) -> YouTubeUpload:
        """Queue a video for upload. Metadata is auto-generated if auto_metadata=True."""
        # 1. Get render output
        render_output = db.query(RenderOutput).get(render_output_id)

        # 2. Auto-generate metadata if requested
        if auto_metadata:
            metadata = await self._generate_metadata(render_output)
        else:
            metadata = provided_metadata

        # 3. Generate thumbnail
        thumbnail_path = await self._generate_thumbnail(render_output, metadata)

        # 4. Create upload record
        upload = YouTubeUpload(
            render_output_id=render_output_id,
            title=metadata["title"],
            description=metadata["description"],
            tags=json.dumps(metadata["tags"]),
            thumbnail_path=thumbnail_path,
            privacy_status=privacy,
            scheduled_time=schedule_time,
            status="pending",
        )
        db.add(upload)
        db.commit()

        # 5. Queue for background processing
        self.queue.append(upload)
        return upload

    async def process_queue(self):
        """Process upload queue (runs as background task)."""
        while True:
            if self.active_uploads < self.max_concurrent and self.queue:
                upload = self.queue.pop(0)
                asyncio.create_task(self._execute_upload(upload))
            await asyncio.sleep(5)

    async def _execute_upload(self, upload: YouTubeUpload):
        """Execute a single upload with retry logic."""
        self.active_uploads += 1
        credential = self._get_credential()
        client = YouTubeClient(credential)

        for attempt in range(3):
            try:
                upload.status = "uploading"
                db.commit()

                video_path = render_output.render_job.output.video_filename
                tags = json.loads(upload.tags) if upload.tags else []

                result = await client.upload_video(
                    video_path=video_path,
                    title=upload.title,
                    description=upload.description,
                    tags=tags,
                    privacy_status=upload.privacy_status,
                    thumbnail_path=upload.thumbnail_path,
                    playlist_id=upload.playlist_id,
                    schedule_time=upload.scheduled_time,
                )

                upload.video_id = result["video_id"]
                upload.video_url = result["url"]
                upload.status = "uploaded"
                upload.uploaded_at = datetime.utcnow()
                db.commit()
                break

            except Exception as e:
                upload.error_message = str(e)
                if attempt < 2:
                    upload.status = "retrying"
                    db.commit()
                    await asyncio.sleep(30 * (attempt + 1))
                else:
                    upload.status = "failed"
                    db.commit()
            finally:
                self.active_uploads -= 1
```

---

## Layer 5: API Endpoints

### New Endpoints (`/api/youtube`)

```
# Authentication
GET    /api/youtube/auth              Generate OAuth2 URL
GET    /api/youtube/callback          Handle OAuth2 callback
GET    /api/youtube/status            Check auth status
POST   /api/youtube/disconnect        Remove stored credentials

# Upload
POST   /api/youtube/upload            Queue a video for upload
POST   /api/youtube/upload/preview    Preview metadata before upload
GET    /api/youtube/uploads           List upload history
GET    /api/youtube/uploads/{id}      Get upload details
DELETE /api/youtube/uploads/{id}      Cancel/delete upload

# Metadata
POST   /api/youtube/metadata/generate Generate title+desc+tags
POST   /api/youtube/thumbnail/generate Generate thumbnail

# Playlists
GET    /api/youtube/playlists         List user's playlists
POST   /api/youtube/playlists         Create playlist

# Analytics
GET    /api/youtube/analytics/{id}    Get video performance
POST   /api/youtube/analytics/sync    Sync analytics for all uploads
```

### API Schemas

```python
# backend/app/schemas/youtube.py

class YouTubeUploadRequest(BaseModel):
    render_output_id: str
    privacy_status: str = "public"  # public, unlisted, private
    playlist_id: str | None = None
    schedule_time: datetime | None = None
    auto_metadata: bool = True
    title: str | None = None          # override auto-generated
    description: str | None = None    # override auto-generated
    tags: list[str] | None = None     # override auto-generated

class YouTubeUploadResponse(BaseModel):
    id: str
    video_id: str | None
    video_url: str | None
    title: str
    description: str | None
    tags: list[str]
    thumbnail_path: str | None
    privacy_status: str
    status: str
    error_message: str | None
    created_at: str
    uploaded_at: str | None

class MetadataPreviewRequest(BaseModel):
    render_output_id: str
    niche: str
    topic: str
    title_override: str | None = None

class MetadataPreviewResponse(BaseModel):
    title: str
    description: str
    tags: list[str]
    hashtags: list[str]
    title_options: list[str]  # 3 alternatives
```

---

## Layer 6: Auto-Upload Integration with Batch Pipeline

### How Auto-Upload Connects to Existing Batch System

```
Batch Job (from auto_gen orchestrator)
    │
    ├─► Scripts Generated
    ├─► TTS Audio Generated
    ├─► Video Rendered
    │
    └─► IF auto_upload=True in BatchConfig:
        │
        ├─► Generate metadata (title, desc, tags, thumbnail)
        ├─► Queue YouTube upload
        ├─► Upload video + thumbnail
        ├─► Store video_id in DB
        └─► Track analytics
```

### BatchConfig Extension

```python
# Add to existing BatchConfig in orchestrator.py
class BatchConfig:
    # ... existing fields ...
    auto_upload: bool = False
    upload_privacy: str = "public"     # public, unlisted, private
    upload_playlist_id: str | None = None
    upload_schedule: str | None = None  # "immediate" or ISO datetime
```

### End-to-End Flow (Zero Intervention)

```
User clicks "Auto Generate & Upload"
    │
    ├─ 1. BATCH CREATION
    │   └─ Creates batch with auto_upload=True
    │
    ├─ 2. SCRIPT GENERATION (automated)
    │   └─ LLM generates scripts for each topic
    │
    ├─ 3. TTS GENERATION (automated)
    │   └─ Kokoro generates audio for each script
    │
    ├─ 4. VIDEO RENDER (automated)
    │   └─ FFmpeg renders MP4 with B-roll + captions
    │
    ├─ 5. METADATA GENERATION (automated)
    │   ├─ LLM generates SEO title
    │   ├─ LLM generates description with hashtags
    │   ├─ Tag generator produces keywords
    │   └─ Thumbnail engine creates banner
    │
    ├─ 6. YOUTUBE UPLOAD (automated)
    │   ├─ OAuth2 token refresh (automatic)
    │   ├─ Resumable upload in chunks
    │   ├─ Custom thumbnail upload
    │   └─ Playlist assignment
    │
    └─ 7. POST-UPLOAD (automated)
        ├─ Store video_id and URL
        ├─ Schedule if needed
        ├─ Start analytics tracking
        └─ Notify user with YouTube URLs
```

---

## Database Schema Additions

```sql
-- YouTube credentials (encrypted tokens)
CREATE TABLE youtube_credentials (
    id TEXT PRIMARY KEY,
    channel_id TEXT,
    channel_title TEXT,
    access_token TEXT NOT NULL,
    refresh_token TEXT NOT NULL,
    token_expiry TIMESTAMP NOT NULL,
    client_id TEXT NOT NULL,
    client_secret TEXT NOT NULL,
    scopes TEXT NOT NULL,
    is_active BOOLEAN DEFAULT 1,
    created_at TIMESTAMP,
    updated_at TIMESTAMP
);

-- YouTube uploads
CREATE TABLE youtube_uploads (
    id TEXT PRIMARY KEY,
    render_output_id TEXT REFERENCES render_outputs(id),
    video_id TEXT,
    video_url TEXT,
    title TEXT NOT NULL,
    description TEXT,
    tags TEXT,                    -- JSON list
    thumbnail_path TEXT,
    privacy_status TEXT DEFAULT 'public',
    playlist_id TEXT,
    scheduled_time TIMESTAMP,
    status TEXT DEFAULT 'pending',
    error_message TEXT,
    youtube_views INTEGER,
    youtube_likes INTEGER,
    youtube_comments INTEGER,
    last_analytics_at TIMESTAMP,
    created_at TIMESTAMP,
    uploaded_at TIMESTAMP
);

-- YouTube playlists cache
CREATE TABLE youtube_playlists (
    id TEXT PRIMARY KEY,
    youtube_playlist_id TEXT NOT NULL,
    title TEXT NOT NULL,
    description TEXT,
    video_count INTEGER DEFAULT 0,
    last_synced_at TIMESTAMP,
    created_at TIMESTAMP
);
```

---

## File Structure (New)

```
backend/app/services/
├── youtube_client.py        # OAuth2 + YouTube Data API v3
├── youtube_uploader.py      # Upload queue, retry, orchestration
├── metadata_generator.py    # Title, description, tags, hashtags
├── thumbnail_engine.py      # Pillow-based thumbnail generation

backend/app/api/
├── youtube.py               # All YouTube API endpoints

backend/app/schemas/
├── youtube.py               # Request/response models

frontend/src/lib/
├── youtubeApi.ts            # YouTube API client

frontend/src/components/
├── YouTubeUploadButton.tsx  # Upload button for render items
├── YouTubeAuthPanel.tsx     # OAuth connection status
├── YouTubeUploadHistory.tsx # Upload list with status
├── MetadataEditor.tsx       # Preview/edit title, desc, tags before upload
├── ThumbnailPreview.tsx     # Preview generated thumbnail
```

---

## Implementation Phases

### Phase 1: Auth Foundation (Week 1)
- [ ] Add YouTubeCredential model + DB migration
- [ ] Implement OAuth2 flow (auth URL, callback, token storage)
- [ ] Implement YouTubeClient with token refresh
- [ ] Add config fields (YOUTUBE_CLIENT_ID, etc.)
- [ ] API: `/auth`, `/callback`, `/status`

### Phase 2: Metadata Engine (Week 2)
- [ ] Implement MetadataGenerator with LLM prompts
- [ ] Build TagGenerator with niche-based tags
- [ ] Build HashtagGenerator
- [ ] Create description templates per niche
- [ ] API: `/metadata/generate`, `/upload/preview`

### Phase 3: Thumbnail Engine (Week 3)
- [ ] Implement ThumbnailEngine with Pillow
- [ ] Create niche-specific style configs
- [ ] Add FFmpeg frame extraction
- [ ] Add text rendering with word wrap
- [ ] API: `/thumbnail/generate`

### Phase 4: Upload Pipeline (Week 4)
- [ ] Implement YouTubeUploader with queue
- [ ] Add resumable upload logic
- [ ] Add retry with exponential backoff
- [ ] Add background task processing
- [ ] API: `/upload`, `/uploads`, `/uploads/{id}`

### Phase 5: Frontend (Week 5)
- [ ] Build YouTubeAuthPanel component
- [ ] Build YouTubeUploadButton (added to RenderHistory)
- [ ] Build MetadataEditor for preview/edit
- [ ] Build ThumbnailPreview
- [ ] Build YouTubeUploadHistory
- [ ] Add upload button to VideoModal

### Phase 6: Batch Integration (Week 6)
- [ ] Extend BatchConfig with auto_upload fields
- [ ] Wire batch pipeline to upload after render
- [ ] Add auto-upload toggle to AutoGenPanel
- [ ] End-to-end test: topic → script → TTS → render → upload
