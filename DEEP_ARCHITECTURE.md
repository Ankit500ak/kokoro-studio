# Kokoro Studio — Deep Architecture
## System Design, Data Flow & Scaling Blueprint

---

# 1. System Overview

Kokoro Studio is a local AI short-video generation platform that converts text scripts into production-ready 9:16 vertical videos with synchronized narration, B-roll footage, yellow title overlays, and real-time word-level captions.

### Core Invariant
```
Audio is the master timeline. Final video duration and caption timing are derived from the audio.
```

### Product Contract
```
INPUT:  Script + Voice + Video Library + Title + Template
PROCESS: TTS → Speech Alignment → Caption Generation → Clip Selection → Timeline → FFmpeg
OUTPUT: 1080x1920 MP4 with narration, B-roll, yellow headline, yellow captions, muted source audio
```

---

# 2. High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                         WEB APPLICATION                             │
│                    React + TypeScript + Vite                         │
│                                                                     │
│  ScriptEditor │ VoiceSelector │ PresetSelector │ SpeedControl       │
│  GenerateButton │ AudioPlayer │ ProjectSelector │ MediaLibrary      │
│  MakeShortButton │ RenderProgress │ TemplateSelector │ LibraryView  │
└───────────────────────────────┬─────────────────────────────────────┘
                                │ HTTP (Vite proxy)
                                ▼
┌─────────────────────────────────────────────────────────────────────┐
│                           API / BFF                                 │
│                    FastAPI + Python 3.11                             │
│                                                                     │
│  TTS │ Projects │ Media │ Templates │ Renders │ Library             │
└──────────────┬──────────────────┬───────────────────┬───────────────┘
               │                  │                   │
               ▼                  ▼                   ▼
        ┌────────────┐     ┌──────────────┐    ┌──────────────┐
        │  SQLite    │     │ Local File   │    │  FFmpeg      │
        │  (metadata)│     │ System       │    │  (render)    │
        └────────────┘     └──────────────┘    └──────────────┘
```

---

# 3. Service Boundaries

The backend is organized as a **modular monolith** with clear service boundaries. Each service has a single responsibility and can be extracted into a独立 service when scale demands it.

```
┌─────────────────────────────────────────────────────────────┐
│                        API LAYER                             │
│  api/tts.py │ api/projects.py │ api/media.py                │
│  api/renders.py │ api/templates.py │ api/library.py         │
└──────────────────────────┬──────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────┐
│                      SERVICE LAYER                           │
│                                                             │
│  ┌─────────────────┐  ┌─────────────────┐                  │
│  │  KokoroService   │  │  RenderService   │                  │
│  │  (TTS Engine)    │  │  (FFmpeg Pipeline)│                  │
│  └────────┬────────┘  └────────┬────────┘                  │
│           │                     │                           │
│  ┌────────▼────────┐  ┌────────▼────────┐                  │
│  │ Voice Blending   │  │ TimelineBuilder  │                  │
│  │ Text Preprocess  │  │   ├── Alignment  │                  │
│  │ Speed Profiles   │  │   ├── Captions   │                  │
│  └─────────────────┘  │   └── ClipSelect  │                  │
│                        └─────────────────┘                  │
└─────────────────────────────────────────────────────────────┘
```

### Service Responsibilities

| Service | Responsibility | Dependencies |
|---------|---------------|--------------|
| `KokoroService` | TTS generation, voice blending, text preprocessing | kokoro.KPipeline, torch, soundfile |
| `RenderService` | FFmpeg rendering, output validation, thumbnails | FFmpeg, FFprobe |
| `TimelineBuilder` | Orchestrate alignment + captions + clips into timeline | SpeechAlignment, CaptionEngine, ClipSelector |
| `SpeechAlignmentService` | Word-level timestamps from audio | whisper CLI (optional) |
| `CaptionEngine` | Segment words into display cues | types.WordTimestamp |
| `CaptionASSGenerator` | Generate ASS subtitle files | types.CaptionCue |
| `ClipSelector` | Select B-roll to match audio duration | models.VideoAsset |

---

# 4. Data Flow: End-to-End Pipeline

## 4.1 TTS Generation Flow

```
User types script
       │
       ▼
ScriptEditor (React)
       │
       │ POST /api/tts/generate
       │ { text, voice, speed, tone, mode, preset, project_id }
       ▼
api/tts.py
       │
       ├─► kokoro_service.generate_speech()
       │     │
       │     ├─► preprocess_text(text, preset)  ← 8 preset engines
       │     ├─► pipeline(text, voice, speed, ...)
       │     ├─► soundfile.write() → storage/audio/{uuid}.wav
       │     └─► return (job_id, filename, duration)
       │
       ├─► GeneratedAudio(id, project_id, filename, voice, ...)
       │     └─► INSERT INTO generated_audio
       │
       └─► TTSResponse { id, filename, voice, duration, ... }
```

## 4.2 Render Pipeline Flow

```
User clicks [MAKE SHORT]
       │
       │ POST /api/renders/
       │ { project_id, generated_audio_id }
       ▼
api/renders.py
       │
       ├─► RenderJob(id, project_id, generated_audio_id, status="queued")
       │     └─► INSERT INTO render_jobs
       │
       └─► background_tasks.add_task(run_render_job, job_id)
             │
             ▼
       RenderService.execute_render(job, db)
             │
             ├─► status → "rendering", stage → "preparing"
             │
             ├─► TimelineBuilder.build_timeline(job, audio, db)
             │     │
             │     ├─► SpeechAlignmentService.align(audio_path, text, duration_ms)
             │     │     └─► WordTimestamp[] (whisper or estimate)
             │     │
             │     ├─► CaptionEngine.generate_cues(words)
             │     │     └─► CaptionCue[] (2-6 words per cue)
             │     │
             │     ├─► ClipSelector.select_clips(db, duration_ms, seed)
             │     │     └─► SelectedClip[] (weighted random, no consecutive repeats)
             │     │
             │     └─► RenderTimeline { duration_ms, audio, video[], title, captions, template }
             │
             ├─► stage → "building_captions"
             │     └─► CaptionASSGenerator.generate_ass(captions)
             │           └─► storage/renders/{job_id}.ass
             │
             ├─► stage → "rendering"
             │     └─► _render_with_ffmpeg(timeline, ass_path, output_path)
             │           │
             │           ├─ Build FFmpeg command:
             │           │   -i video_clip_1 ... -i video_clip_N -i audio.wav
             │           │   filter: scale → pad → concat → drawtext (title) → ass (captions)
             │           │   -map [vout] -map N:a
             │           │   -c:v libx264 -c:a aac -shortest
             │           │
             │           └─► storage/renders/{job_id}.mp4
             │
             ├─► stage → "validating_output"
             │     └─► _validate_output(path, expected_duration)
             │           ├─ File exists + size > 1KB
             │           ├─ FFprobe: has video + audio streams
             │           └─ Duration within 50ms tolerance
             │
             ├─► _generate_thumbnail(video_path, thumb_path)
             │     └─► storage/renders/{job_id}_thumb.jpg
             │
             ├─► RenderOutput { video_filename, thumbnail_filename, duration, ... }
             │     └─► INSERT INTO render_outputs
             │
             └─► job.status → "completed", progress → 100%
```

---

# 5. Database Schema (SQLite)

## Entity Relationship Diagram

```
┌──────────────┐       ┌──────────────────┐
│   Project    │──1:N──│  GeneratedAudio   │
│              │       │                  │
│  id (PK)     │       │  id (PK)         │
│  name        │       │  project_id (FK) │
│  title       │       │  filename        │
│  script_text │       │  voice           │
│  status      │       │  mode, preset    │
│  created_at  │       │  text, duration  │
│  updated_at  │       │  speed, tone     │
└──────┬───────┘       │  file_size       │
       │               │  status          │
       │               │  created_at      │
       │               └──────────────────┘
       │
       │──1:N──┌──────────────────┐       ┌──────────────────┐
       │       │    RenderJob     │──1:1──│   RenderOutput   │
       │       │                  │       │                  │
       │       │  id (PK)         │       │  id (PK)         │
       │       │  project_id (FK) │       │  render_job_id   │
       │       │  generated_audio │       │  video_filename  │
       │       │    _id (FK)      │       │  thumb_filename  │
       │       │  status, progress│       │  duration        │
       │       │  render_seed     │       │  width, height   │
       │       │  timeline_data   │       │  file_size       │
       │       │  started_at      │       │  codec           │
       │       │  completed_at    │       │  created_at      │
       │       └──────────────────┘       └──────────────────┘
       │
       └──────────────────────────┌──────────────────┐
                                  │   VideoAsset     │
                                  │  (standalone)    │
                                  │                  │
                                  │  id (PK)         │
                                  │  filename        │
                                  │  duration        │
                                  │  width, height   │
                                  │  fps, codec      │
                                  │  tags, category  │
                                  │  usage_count     │
                                  │  status          │
                                  └──────────────────┘

┌──────────────────┐
│    Template      │  (standalone)
│                  │
│  id (PK)         │
│  name            │
│  version         │
│  config (JSON)   │
│  is_default      │
│  resolution_*    │
│  fps             │
└──────────────────┘
```

## Key Design Decisions

| Decision | Rationale |
|----------|-----------|
| `GeneratedAudio.project_id` nullable | Audio can exist standalone (quick generate) or linked to a project |
| `RenderJob.generated_audio_id` FK | Render consumes audio; audio is immutable once rendered |
| `VideoAsset` standalone | B-roll assets are global, reusable across projects |
| `Template.config` as JSON string | Flexible schema for template evolution without migrations |
| `RenderJob.render_seed` | Ensures reproducible renders for the same inputs |

---

# 6. API Surface (30 Endpoints)

## TTS (`/api`)
| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/health` | Pipeline health check |
| GET | `/api/voices` | List voices (filter: gender, weight) |
| GET | `/api/voices/weight/{weight}` | Voices by weight category |
| GET | `/api/voices/{voice_id}` | Single voice details |
| GET | `/api/tone-presets` | Tone preset definitions |
| POST | `/api/tts/preview` | Quick voice preview |
| POST | `/api/tts/generate` | Full TTS generation |
| GET | `/api/audio/{filename}` | Serve WAV file |

## Library (`/api/library`)
| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/library/` | Paginated audio list |
| GET | `/api/library/stats` | Aggregate statistics |
| GET | `/api/library/{audio_id}` | Single audio metadata |
| GET | `/api/library/{audio_id}/file` | Serve audio file |
| DELETE | `/api/library/{audio_id}` | Delete audio + file |

## Projects (`/api/projects`)
| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/projects/` | List projects |
| POST | `/api/projects/` | Create project |
| GET | `/api/projects/{id}` | Get project |
| PATCH | `/api/projects/{id}` | Update project |
| DELETE | `/api/projects/{id}` | Delete project + cascade |

## Media (`/api/media`)
| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/media/` | List video assets |
| POST | `/api/media/upload` | Upload + FFprobe analyze |
| GET | `/api/media/{id}` | Get asset metadata |
| GET | `/api/media/{id}/file` | Serve video file |
| PATCH | `/api/media/{id}` | Update tags/category |
| DELETE | `/api/media/{id}` | Delete asset + file |

## Renders (`/api/renders`)
| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/renders/` | List render jobs |
| POST | `/api/renders/` | Create render (async) |
| GET | `/api/renders/{id}` | Get job status |
| GET | `/api/renders/{id}/output` | Get output metadata |
| GET | `/api/renders/{id}/file` | Download MP4 |
| GET | `/api/renders/{id}/thumbnail` | Get thumbnail |
| POST | `/api/renders/{id}/retry` | Retry failed job |

## Templates (`/api/templates`)
| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/templates/` | List templates |
| POST | `/api/templates/` | Create template |
| GET | `/api/templates/defaults` | Get default template |
| GET | `/api/templates/{id}` | Get template |
| PATCH | `/api/templates/{id}` | Update (auto-increment version) |
| DELETE | `/api/templates/{id}` | Delete (blocks default) |

---

# 7. Component Architecture (React)

## State Management

```
Zustand Store (useStore.ts)
├── text: string
├── voice: string
├── speed: number
├── tone: string
├── preset: ContentPresetId
├── isGenerating: boolean
├── generatedAudio: GeneratedAudio | null
├── history: GeneratedAudio[]
├── voices: Voice[]
├── error: string | null
└── Actions: setText, setVoice, setSpeed, setTone, setPreset, ...

LocalStorage Persistence
└── history (generated audio records)
```

## Component Tree

```
App
├── Header (sticky)
│   ├── Logo + Title
│   ├── Active Preset Badge
│   ├── Library Scroll Button
│   ├── Voice Count Badge
│   └── Status Indicator
│
├── Main Grid (1:3 ratio on desktop)
│   ├── Left Column
│   │   ├── ProjectSelector
│   │   │   └── Inline create/edit/delete
│   │   ├── ScriptEditor
│   │   │   ├── Textarea
│   │   │   ├── Word/Char count
│   │   │   └── Duration estimate
│   │   ├── GenerateButton
│   │   │   ├── Loading state
│   │   │   └── Error display
│   │   ├── AudioPlayer
│   │   │   ├── Waveform
│   │   │   └── Download
│   │   └── MakeShortButton
│   │       └── Requires: project + audio
│   │
│   └── Right Column
│       ├── PresetSelector (8 presets)
│       ├── VoiceSelector
│       │   ├── Gender filters
│       │   ├── Weight filters
│       │   └── Voice cards
│       ├── SpeedControl
│       │   ├── Speed slider
│       │   └── Tone buttons
│       ├── TemplateSelector
│       │   └── Config preview
│       └── MediaLibrary
│           ├── Drag-drop upload
│           └── Asset list
│
├── RenderProgress (conditional)
│   ├── Progress bar
│   ├── Stage labels
│   ├── Download button
│   └── Retry button
│
└── Bottom Section
    ├── LibraryView (server-side)
    ├── RenderHistory
    └── History (local)
```

---

# 8. Render Pipeline Deep Dive

## 8.1 Speech Alignment

```
Input:  audio.wav + script text + duration_ms
Output: WordTimestamp[]

Strategy:
  1. If whisper CLI available → use word_timestamps=True
  2. Otherwise → character-based estimation:
     - Count words and total characters
     - Calculate ms_per_char = duration / total_chars
     - Each word gets: start_ms = cumulative, end_ms = start + char_count * ms_per_char
     - Add 0.3 * ms_per_char gap between words
```

## 8.2 Caption Segmentation Rules

```
Input:  WordTimestamp[]
Output: CaptionCue[]

Rules:
  - 2-6 words per cue (configurable)
  - Maximum 2 lines
  - Minimum cue duration: 650ms
  - Maximum cue duration: 2600ms
  - Break on sentence-ending punctuation (. ! ?)
  - Break on comma if 2+ words accumulated
  - Never split contractions
  - Words are uppercased for display
```

## 8.3 ASS Subtitle Format

```ass
[Script Info]
PlayResX: 1080
PlayResY: 1920

[V4+ Styles]
Style: Default,Arial,52,&H0000FFFF,&H000000FF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,4,2,2,20,20,120,1

[Events]
Dialogue: 0,0:00:00.00,0:00:02.50,Default,,0,0,0,,I TOOK THE JOB
Dialogue: 0,0:00:02.50,0:00:05.00,Default,,0,0,0,,BECAUSE I WAS BROKE
```

## 8.4 Clip Selection Algorithm

```
Input:  VideoAsset[], target_duration_ms, seed
Output: SelectedClip[]

Algorithm:
  1. Query VideoAsset WHERE status='ready' AND duration >= 2s
  2. Order by usage_count ASC (prefer less-used)
  3. For each iteration:
     a. Filter out last-used asset (prevent consecutive repeats)
     b. Weight by 1/(usage_count + 1)
     c. Weighted random selection
     d. Determine clip duration: min(asset_duration, remaining_ms)
     e. Random start position if asset longer than needed
     f. Update asset.usage_count++
  4. Continue until target_duration filled
  5. Commit usage count updates
```

## 8.5 FFmpeg Render Command

```bash
ffmpeg -y \
  -ss {start} -t {duration} -i clip1.mp4 \
  -ss {start} -t {duration} -i clip2.mp4 \
  ... \
  -i audio.wav \
  -filter_complex "
    [0:v]scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:(ow-iw)/2:(oh-ih)/2,setsar=1,fps=30[v0];
    [1:v]scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:(ow-iw)/2:(oh-ih)/2,setsar=1,fps=30[v1];
    [v0][v1]concat=n=2:v=1:a=0[vconcat];
    [vconcat]drawtext=text='TITLE':fontcolor=#FFD400:fontsize=64:x=(w-text_w)/2:y=100:borderw=4:bordercolor=black[vtitle];
    [vtitle]ass='render.job.ass'[vout]
  " \
  -map "[vout]" \
  -map "2:a" \
  -c:v libx264 -preset fast -crf 23 \
  -c:a aac -b:a 128k \
  -shortest \
  -movflags +faststart \
  output.mp4
```

## 8.6 Output Validation

```
Checks (all must pass):
  1. File exists
  2. File size > 1KB
  3. FFprobe: has video stream
  4. FFprobe: has audio stream
  5. Duration within 50ms OR 2% of expected (whichever is larger)
```

---

# 9. Content Preset System

## 9.1 Preset Definitions

| Preset | Speed | Tone | Mode | Text Preprocessing |
|--------|-------|------|------|--------------------|
| Shorts | 1.12x | bright | shorts | Hook-driven, fast fragments |
| Story | 0.95x | natural | storytelling | Dramatic pauses, emotional |
| Mystery | 0.88x | deep | storytelling | Trailing dots, slow fragmentation |
| Documentary | 0.90x | deep | storytelling | Measured, no drama |
| Horror | 0.82x | deep | storytelling | Sentence fragmentation, max pauses |
| Romantic | 0.92x | gentle | storytelling | Gentle flow, soft pauses |
| Educational | 1.0x | warm | storytelling | Clear, friendly pacing |
| News | 1.05x | crisp | shorts | Filler removal, crisp delivery |

## 9.2 Text Preprocessing Pipeline

```
Input: raw script text + preset ID
Output: processed text

Each preset has its own preprocessing function:
  - preprocess_text_shorts(): Hook-first, 60-char fragments, remove fillers
  - preprocess_text_storytelling(): Dramatic pauses, 80-char fragments
  - preprocess_text_mystery(): Extra dots, 2-sentence pauses, slow fragmentation
  - preprocess_text_horror(): 50-char fragments, pause EVERY sentence
  - preprocess_text_romantic(): Gentle flow, 100-char fragments
  - preprocess_text_documentary(): 90-char fragments, no drama
  - preprocess_text_educational(): 80-char fragments, clear breaks
  - preprocess_text_news(): Filler removal, 60-char fragments
```

## 9.3 Voice Profiles

```python
VOICE_PROFILES = {
    "am_adam": {
        "blend": None,  # No blending
        "storytelling": {
            "speed_offset": -0.03,
            "split_pattern": r"\n\n+",
            "speed_fn": lambda count: 0.95 + (count * -0.001)
        },
        "shorts": {
            "speed_offset": +0.05,
            "split_pattern": r"(?<=[.!?])\s+",
            "speed_fn": lambda count: 1.05 + (count * 0.001)
        }
    },
    # ... 14 voices total (7M + 7F)
}
```

---

# 10. Template System

## 10.1 Default Yellow Story Template

```json
{
  "canvas": { "width": 1080, "height": 1920, "fps": 30 },
  "title": {
    "color": "#FFD400",
    "position": "top",
    "maxLines": 3,
    "fontWeight": 800,
    "fontSize": 64
  },
  "captions": {
    "color": "#FFD400",
    "position": "bottom-center",
    "maxWords": 5,
    "maxLines": 2,
    "outline": "#000000",
    "outlineWidth": 4,
    "fontSize": 52
  },
  "audio": { "sourceVideoAudio": false }
}
```

## 10.2 Template Versioning

- Templates have a `version` integer (starts at 1)
- Updating `config` auto-increments version
- Old renders reference the template version they used
- Never silently modify an existing template version

---

# 11. Storage Layout

```
backend/storage/
├── kokoro.db                  # SQLite database
├── audio/                     # Generated WAV files
│   ├── {uuid1}.wav
│   ├── {uuid2}.wav
│   └── ...
├── previews/                  # Quick preview WAVs
│   ├── {uuid}_preview.wav
│   └── ...
├── media/                     # Uploaded B-roll videos
│   ├── {uuid}.mp4
│   ├── {uuid}.webm
│   └── ...
└── renders/                   # Rendered outputs
    ├── {job_id}.mp4           # Final video
    ├── {job_id}_thumb.jpg     # Thumbnail
    ├── {job_id}.ass           # Subtitle file
    └── ...
```

---

# 12. Scaling Path

## Current: Local Monolith
```
SQLite + Local Storage + FastAPI + Vite Dev Server
```

## Phase 2: Production Monolith
```
PostgreSQL + S3/R2 + FastAPI + Vite Build + Nginx
```

## Phase 3: Distributed Workers
```
Redis + BullMQ + Worker Pool (TTS, Alignment, Render)
```

## Phase 4: Microservices
```
TTS Service │ Render Service │ Media Service │ API Gateway
```

---

# 13. Critical Engineering Principles

| # | Principle | Implementation |
|---|-----------|----------------|
| 1 | Audio is authoritative | `FINAL_DURATION = AUDIO_DURATION` — everything derives from audio |
| 2 | Rendering is async | `BackgroundTasks` — never block API on FFmpeg |
| 3 | Media in object storage | Files on disk (S3-ready path structure) |
| 4 | Workers are disposable | Jobs can retry from any stage |
| 5 | Rendering is reproducible | `render_seed` + template version stored |
| 6 | Providers are abstractions | `SpeechAlignmentService` swappable (whisper → custom) |
| 7 | Templates are versioned | Config changes increment version |
| 8 | Validation post-render | FFprobe check + duration tolerance |

---

# 14. Known Limitations & Future Work

| Area | Current | Target |
|------|---------|--------|
| Auth | None | JWT + user scoping |
| Database | SQLite | PostgreSQL |
| Storage | Local disk | S3/R2 with signed URLs |
| Queue | BackgroundTasks | Redis + BullMQ |
| Progress | Polling (2s) | Server-Sent Events |
| Speech Alignment | Whisper CLI or estimate | Dedicated alignment service |
| B-Roll Selection | Random + usage weight | Semantic similarity (embeddings) |
| Word Highlighting | Not in ASS | Frame-based composition layer |
| Templates | 1 default | User-creatable, marketplace |
| Caching | None | Redis for TTS hash cache |
| Rate Limiting | None | slowapi (in requirements, unused) |
| Tests | None | Unit + Integration + E2E |
| CI/CD | None | GitHub Actions |
| Docker | None | docker-compose.yml |

---

# 15. File Inventory

## Backend (31 files)
```
backend/
├── app/
│   ├── __init__.py
│   ├── main.py                          # FastAPI app + router registration
│   ├── api/
│   │   ├── __init__.py
│   │   ├── tts.py                       # TTS endpoints (8 routes)
│   │   ├── library.py                   # Audio library CRUD (5 routes)
│   │   ├── projects.py                  # Project CRUD (5 routes)
│   │   ├── media.py                     # Video asset CRUD (6 routes)
│   │   ├── renders.py                   # Render job management (7 routes)
│   │   └── templates.py                 # Template CRUD (6 routes)
│   ├── core/
│   │   ├── __init__.py
│   │   ├── config.py                    # Settings + constants
│   │   ├── database.py                  # SQLAlchemy engine + session
│   │   ├── models.py                    # 6 ORM models
│   │   └── voices.json                  # 14 voice definitions
│   ├── schemas/
│   │   ├── __init__.py
│   │   ├── tts.py                       # TTS request/response
│   │   ├── library.py                   # Library response models
│   │   ├── project.py                   # Project schemas
│   │   ├── video.py                     # Video asset schemas
│   │   ├── render.py                    # Render job schemas
│   │   └── template.py                  # Template schemas
│   └── services/
│       ├── __init__.py
│       ├── types.py                     # Dataclasses (8 types)
│       ├── kokoro_service.py            # TTS engine
│       ├── render_service.py            # FFmpeg pipeline
│       ├── speech_alignment.py          # Word timestamps
│       ├── caption_engine.py            # Caption segmentation + ASS
│       ├── clip_selector.py             # B-roll selection
│       └── timeline_builder.py          # Timeline orchestration
├── requirements.txt
├── .env.example
└── storage/                             # Runtime data (gitignored)
```

## Frontend (20 files)
```
frontend/
├── src/
│   ├── main.tsx                         # React entry + ErrorBoundary
│   ├── App.tsx                          # Root component
│   ├── index.css                        # Global Tailwind styles
│   ├── types/
│   │   └── index.ts                     # All TypeScript types + presets
│   ├── hooks/
│   │   ├── useStore.ts                  # Zustand state management
│   │   └── useTTS.ts                    # TTS API hook
│   └── components/
│       ├── ScriptEditor.tsx             # Text input + counts
│       ├── VoiceSelector.tsx            # Voice picker + filters
│       ├── PresetSelector.tsx           # 8-preset grid
│       ├── SpeedControl.tsx             # Speed slider + tones
│       ├── GenerateButton.tsx           # Generate trigger
│       ├── AudioPlayer.tsx              # Audio playback
│       ├── History.tsx                  # Local generation history
│       ├── LibraryView.tsx              # Server-side audio library
│       ├── ProjectSelector.tsx          # Project CRUD
│       ├── MediaLibrary.tsx             # Video upload + list
│       ├── MakeShortButton.tsx          # Render trigger
│       ├── RenderProgress.tsx           # Live render progress
│       ├── TemplateSelector.tsx         # Template picker
│       └── RenderHistory.tsx            # Past renders list
├── package.json
├── vite.config.ts
├── tailwind.config.js
├── tsconfig.json
└── index.html
```

---

# 16. Dependency Graph

```
Backend:
  FastAPI ─── SQLAlchemy ─── SQLite
      │
      ├── kokoro.KPipeline ─── torch ─── soundfile
      │
      └── FFmpeg/FFprobe (external binary)

Frontend:
  React 18 ─── Zustand ─── localStorage
      │
      ├── Tailwind CSS
      ├── lucide-react (icons)
      ├── wavesurfer.js (audio visualization)
      └── Vite (dev server + proxy)
```
