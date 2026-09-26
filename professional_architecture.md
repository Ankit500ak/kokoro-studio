# AI Short Video Generation Platform
## Production-Grade Architecture & Engineering Specification

> **Product:** Automated short-form video generation from script + generated voice + reusable video assets.
>
> **Primary output:** Vertical 9:16 MP4 with synchronized narration, randomized/relevance-aware B-roll, yellow title, and real-time word-level captions.
>
> **Core invariant:** Audio is the master timeline. Final video duration and caption timing are derived from the audio.

---

# 1. Executive Architecture

```text
┌─────────────────────────────────────────────────────────────────────┐
│                         WEB APPLICATION                             │
│                    Next.js + React + TypeScript                     │
│                                                                     │
│  Script Editor │ Voice Generator │ Project │ Media Library │ Jobs  │
└───────────────────────────────┬─────────────────────────────────────┘
                                │ HTTPS
                                ▼
┌─────────────────────────────────────────────────────────────────────┐
│                           API / BFF                                 │
│                    Node.js + TypeScript                             │
│                                                                     │
│ Auth │ Projects │ TTS │ Media │ Templates │ Render Jobs │ Webhooks │
└──────────────┬──────────────────┬───────────────────┬───────────────┘
               │                  │                   │
               ▼                  ▼                   ▼
        ┌────────────┐     ┌──────────────┐    ┌──────────────┐
        │ PostgreSQL │     │ Object Store │    │    Redis     │
        │ + Prisma   │     │ S3/R2/etc.   │    │   + BullMQ   │
        └────────────┘     └──────────────┘    └──────┬───────┘
                                                       │
                                                       ▼
                              ┌────────────────────────────────┐
                              │        WORKER CLUSTER          │
                              │                                │
                              │ TTS Worker                     │
                              │ Speech Alignment Worker        │
                              │ Media Analysis Worker          │
                              │ Timeline Worker                │
                              │ Render Worker                   │
                              │ Thumbnail Worker               │
                              └───────────────┬────────────────┘
                                              │
                                              ▼
                              ┌────────────────────────────────┐
                              │       MEDIA PIPELINE            │
                              │                                │
                              │ FFmpeg │ ASS │ Fonts │ Filters │
                              └───────────────┬────────────────┘
                                              │
                                              ▼
                              ┌────────────────────────────────┐
                              │       FINAL MEDIA ASSETS        │
                              │ MP4 │ Thumbnail │ Metadata      │
                              └────────────────────────────────┘
```

---

# 2. Product Workflow

The user experience should remain extremely simple:

```text
Create Project
      ↓
Write / Paste Script
      ↓
Generate Voice
      ↓
Voice Ready
      ↓
[ MAKE SHORT ]
      ↓
Analyze Speech
      ↓
Generate Word Timestamps
      ↓
Build Caption Timeline
      ↓
Select B-Roll
      ↓
Build Visual Timeline
      ↓
Apply Template
      ↓
Render
      ↓
Preview
      ↓
Download / Regenerate
```

The user should not have to manually edit a timeline for the MVP.

---

# 3. Domain Model

The application should be organized around these domain entities:

```text
User
 └── Project
      ├── Script
      ├── VoiceAsset
      ├── CaptionTrack
      ├── RenderJob
      └── RenderOutput

User
 ├── VideoAsset
 └── Template
```

## Core entities

### User

```text
id
email
name
createdAt
updatedAt
```

### Project

```text
id
userId
name
scriptText
title
status
createdAt
updatedAt
```

### AudioAsset

```text
id
projectId
storageKey
durationMs
sampleRate
channels
format
provider
providerMetadata
createdAt
```

### VideoAsset

```text
id
userId
storageKey
durationMs
width
height
fps
codec
orientation
fileSize
checksum
tags
category
usageCount
lastUsedAt
status
createdAt
```

### Template

```text
id
userId
name
version
aspectRatio
resolution
fps
titleConfig
captionConfig
transitionConfig
createdAt
updatedAt
```

### RenderJob

```text
id
projectId
templateId
status
progress
currentStage
attempt
errorCode
errorMessage
startedAt
completedAt
createdAt
```

### RenderOutput

```text
id
renderJobId
videoStorageKey
thumbnailStorageKey
durationMs
width
height
fileSize
codec
createdAt
```

---

# 4. Service Boundaries

Do not build one giant backend service.

Use logical service boundaries even if the MVP is deployed as a modular monolith.

```text
AuthModule
ProjectModule
AudioModule
TTSModule
SpeechAlignmentModule
MediaModule
TemplateModule
TimelineModule
RenderModule
JobModule
StorageModule
```

Later, expensive components can become independent services.

---

# 5. Recommended Technology Stack

## Frontend

```text
Next.js
React
TypeScript
Tailwind CSS
TanStack Query
Zod
```

Responsibilities:

- Project creation
- Script editing
- Voice generation
- Audio preview
- Make Short action
- Render progress
- Media library
- Template selection
- Video preview
- Download/regenerate

---

## Backend

```text
Node.js
TypeScript
Fastify or NestJS
Prisma
PostgreSQL
Zod
```

Use strict request/response validation.

---

## Queue

```text
Redis
BullMQ
```

Queue categories:

```text
tts
speech-alignment
media-analysis
timeline
render
thumbnail
cleanup
```

---

## Media Processing

```text
FFmpeg
FFprobe
ASS subtitles
ImageMagick or equivalent thumbnail tooling
```

Use FFprobe before rendering to inspect uploaded media.

---

## Storage

Production options:

```text
Amazon S3
Cloudflare R2
Supabase Storage
```

Object storage should contain media, not PostgreSQL.

---

# 6. API Architecture

Use versioned APIs:

```text
/api/v1
```

## Projects

```http
POST   /api/v1/projects
GET    /api/v1/projects
GET    /api/v1/projects/:id
PATCH  /api/v1/projects/:id
DELETE /api/v1/projects/:id
```

## Voice

```http
POST /api/v1/projects/:id/voice
GET  /api/v1/projects/:id/audio
```

## Short generation

```http
POST /api/v1/projects/:id/renders
GET  /api/v1/renders/:id
POST /api/v1/renders/:id/retry
POST /api/v1/renders/:id/regenerate
```

## Media

```http
POST   /api/v1/media/upload-url
POST   /api/v1/media/complete
GET    /api/v1/media
PATCH  /api/v1/media/:id
DELETE /api/v1/media/:id
```

## Templates

```http
GET  /api/v1/templates
POST /api/v1/templates
GET  /api/v1/templates/:id
PATCH /api/v1/templates/:id
```

---

# 7. Upload Architecture

Never upload large videos through the API server.

Use direct-to-storage uploads.

```text
Browser
   │
   │ Request signed URL
   ▼
API
   │
   │ Signed upload URL
   ▼
Browser ───────────────► Object Storage
                            │
                            ▼
                      Upload Complete
                            │
                            ▼
                           API
                            │
                            ▼
                     Media Analysis Job
```

Benefits:

- Lower API bandwidth
- Better reliability
- Large file support
- Easier horizontal scaling

---

# 8. Media Ingestion Pipeline

When a video is uploaded:

```text
Upload
  ↓
Checksum
  ↓
File Validation
  ↓
FFprobe
  ↓
Metadata Extraction
  ↓
Thumbnail Extraction
  ↓
Optional Transcode
  ↓
Tagging
  ↓
READY
```

Validate:

```text
MIME type
container
codec
duration
resolution
file size
FPS
audio streams
```

Do not trust filename extensions.

---

# 9. Voice Generation Pipeline

When the user clicks Generate Voice:

```text
Script
  ↓
Validate
  ↓
TTS Provider
  ↓
Audio File
  ↓
Store Object
  ↓
Read Duration
  ↓
Create AudioAsset
  ↓
VOICE_READY
```

TTS must be provider-agnostic.

```typescript
interface TTSProvider {
  synthesize(input: TTSRequest): Promise<TTSResult>;
}
```

Possible providers can be plugged in without changing the rest of the system.

---

# 10. "MAKE SHORT" Trigger

The Make Short button appears only after valid audio exists.

Frontend:

```text
VOICE_READY
     ↓
Show [ MAKE SHORT ]
```

Clicking it creates a render job:

```http
POST /api/v1/projects/:projectId/renders
```

Example response:

```json
{
  "renderId": "rnd_01J...",
  "status": "QUEUED"
}
```

The API should return immediately.

Never keep the HTTP request open during FFmpeg rendering.

---

# 11. Render State Machine

```text
QUEUED
  ↓
PREPARING
  ↓
ANALYZING_AUDIO
  ↓
BUILDING_CAPTIONS
  ↓
SELECTING_CLIPS
  ↓
BUILDING_TIMELINE
  ↓
RENDERING
  ↓
VALIDATING_OUTPUT
  ↓
UPLOADING
  ↓
COMPLETED
```

Failure from any state:

```text
FAILED
```

Retryable jobs:

```text
FAILED → RETRYING → PREPARING
```

Non-retryable validation errors should stop immediately.

---

# 12. Audio as Master Timeline

This is the most important architectural rule.

```text
FINAL_DURATION = AUDIO_DURATION
```

Example:

```text
Voice = 63.72 seconds

Final video = 63.72 seconds
```

Every other timeline element is constrained by this duration.

---

# 13. Speech Alignment

The system must obtain word-level timing.

Target model:

```typescript
interface WordTimestamp {
  id: string;
  text: string;
  startMs: number;
  endMs: number;
  confidence?: number;
}
```

Example:

```json
{
  "text": "broke",
  "startMs": 420,
  "endMs": 910
}
```

The alignment provider should be replaceable:

```typescript
interface SpeechAlignmentProvider {
  align(audio: AudioAsset): Promise<WordTimestamp[]>;
}
```

Do not tie the renderer directly to one speech provider.

---

# 14. Caption Engine

Build a dedicated caption engine.

Input:

```text
WordTimestamp[]
```

Output:

```typescript
interface CaptionCue {
  startMs: number;
  endMs: number;
  words: CaptionWord[];
}
```

Each word retains its original timing.

---

# 15. Caption Segmentation Rules

The caption engine should optimize for readability.

Default rules:

```text
2-6 words per cue
maximum 2 lines
minimum readable duration
respect punctuation
respect phrase boundaries
avoid orphan words
avoid splitting contractions
```

The engine should be configurable.

Example:

```json
{
  "maxWords": 5,
  "maxLines": 2,
  "minCueDurationMs": 650,
  "maxCueDurationMs": 2600
}
```

---

# 16. Real-Time Caption Rendering

Use word-level timestamps to create the visual state.

Example:

```text
I WAS BROKE
        ↑
     CURRENT
```

The renderer should highlight the current spoken word/phrase.

Recommended default:

```text
Base text:
yellow

Current word:
yellow + slight scale/emphasis

Outline:
black

Shadow:
enabled
```

Caption positioning:

```text
bottom-center
```

with configurable safe-area margins.

---

# 17. Title System

The title is a separate overlay layer.

Example:

```text
THE PAINTING
THAT PREDICTED
THE MARKET
```

Configuration:

```typescript
interface TitleStyle {
  color: string;
  fontFamily: string;
  fontSize: number;
  fontWeight: number;
  position: "top" | "center" | "bottom";
  maxLines: number;
  stroke: boolean;
}
```

Default:

```text
Color: yellow
Position: top
Weight: bold
Max lines: 3
```

---

# 18. Video Selection Engine

Do not use naive random selection.

The selection engine should consider:

```text
randomness
semantic relevance
recent usage
duplicate prevention
duration fit
asset quality
```

Example conceptual score:

```text
score =
    relevanceWeight * relevance
  + randomWeight * random
  + qualityWeight * quality
  - repetitionWeight * repetition
  - recentWeight * recency
```

The selector returns:

```typescript
interface SelectedClip {
  assetId: string;
  sourceStartMs: number;
  sourceEndMs: number;
  timelineStartMs: number;
  timelineEndMs: number;
}
```

---

# 19. Clip Selection Constraints

Required:

```text
Never use same clip consecutively.
Avoid excessive repetition.
Prefer unused/recently unused clips.
Fill entire audio duration.
Trim final clip when necessary.
Loop only when the library is insufficient.
```

Example:

```text
Audio: 42s

Clip A: 6s
Clip F: 8s
Clip C: 4s
Clip H: 7s
Clip D: 9s
Clip B: 8s

Total: 42s
```

---

# 20. Semantic B-Roll Matching

MVP:

```text
random + tags
```

Later:

```text
Script
 ↓
Sentence embeddings
 ↓
Video asset embeddings
 ↓
Similarity score
 ↓
Candidate pool
 ↓
Weighted random selection
```

This gives randomness without destroying relevance.

---

# 21. Timeline Builder

The Timeline Builder converts all components into one deterministic object.

```typescript
interface RenderTimeline {
  durationMs: number;

  audio: AudioLayer;

  video: VideoSegment[];

  title?: TitleLayer;

  captions: CaptionCue[];

  template: TemplateConfig;
}
```

Example:

```text
0 ───────────────────────────── 60s

VIDEO
[A][B][C][D][E][F]

AUDIO
[──────────────────────────────]

TITLE
[──────────────────────────────]

CAPTIONS
[1][2][3][4][5][6][7]...
```

The renderer should consume only this timeline.

---

# 22. Deterministic Rendering

Once a timeline is generated, rendering must be deterministic.

Store:

```text
render seed
selected asset IDs
source clip ranges
caption timestamps
template version
audio asset version
renderer version
```

This allows the exact same render to be reproduced.

---

# 23. Regeneration

Regenerate should create a new seed:

```text
same audio
same captions
same title
same template
different clip selection
```

This enables multiple visual variants without regenerating expensive TTS.

---

# 24. Render Engine

Use FFmpeg as the primary production renderer.

Responsibilities:

```text
Input normalization
Scale
Crop
Trim
Concat
Mute source audio
Overlay title
Render captions
Mix final audio
Encode
Thumbnail
```

Recommended output:

```text
1080x1920
30 FPS
H.264
AAC
MP4
yuv420p
```

---

# 25. Caption Rendering Strategy

For MVP:

```text
ASS subtitle generation
        ↓
FFmpeg subtitles filter
```

Advantages:

- Precise timestamps
- Styling
- Word highlighting
- Font control
- Repeatable rendering

For advanced animation:

```text
Frame-based composition layer
```

can be introduced later.

---

# 26. Render Command Abstraction

Do not scatter FFmpeg commands throughout the codebase.

Create:

```text
FFmpegService
```

with methods:

```typescript
probe(file)
normalize(input, output)
crop(input, output, config)
concat(inputs, output)
renderSubtitles(input, ass, output)
muxAudio(video, audio, output)
thumbnail(video, output)
```

This makes the media layer testable.

---

# 27. Worker Architecture

Workers should be independently scalable.

```text
Redis
 │
 ├── TTS Queue
 │     └── TTS Workers
 │
 ├── Alignment Queue
 │     └── Alignment Workers
 │
 ├── Media Queue
 │     └── Media Workers
 │
 ├── Render Queue
 │     └── Render Workers
 │
 └── Cleanup Queue
       └── Cleanup Workers
```

Render workers should have FFmpeg installed and appropriate CPU/memory limits.

---

# 28. Job Idempotency

Every expensive operation should be idempotent.

Use:

```text
idempotencyKey
```

Example:

```text
projectId
+
audioAssetId
+
templateVersion
+
renderSeed
```

If the same render is submitted twice, the system should avoid accidental duplicate processing where possible.

---

# 29. Storage Layout

Recommended:

```text
bucket/
├── users/
│   └── {userId}/
│       ├── uploads/
│       ├── audio/
│       ├── renders/
│       └── thumbnails/
│
└── system/
    ├── fonts/
    └── templates/
```

Use storage keys rather than public URLs inside the database.

Generate signed URLs when users need access.

---

# 30. Database Rules

PostgreSQL stores:

```text
metadata
relationships
configuration
job state
timestamps
references
```

Object storage stores:

```text
MP4
WAV
MP3
thumbnails
ASS
temporary media
```

Never store full video blobs in PostgreSQL.

---

# 31. Security Architecture

Required:

```text
Authentication
Authorization
Signed upload URLs
Signed download URLs
Rate limiting
File validation
Virus/malware scanning where appropriate
FFmpeg sandboxing
Resource limits
Job ownership checks
```

Every project/media/render query must be scoped to the authenticated user.

---

# 32. Resource Protection

Uploaded media can be malicious or extremely expensive to process.

Enforce:

```text
max upload size
max duration
max resolution
max FPS
max render duration
max concurrent jobs/user
max total storage/user
```

Use worker-level CPU/memory/time limits.

---

# 33. Observability

Production deployment must include:

```text
Structured logs
Metrics
Distributed tracing
Error tracking
Job monitoring
Render timing
Storage metrics
```

Track:

```text
TTS latency
alignment latency
clip selection latency
render latency
upload latency
failure rate
queue depth
average render duration
CPU utilization
```

Every job should have:

```text
requestId
jobId
projectId
userId
```

for traceability.

---

# 34. Render Progress

Frontend should receive progress via:

```text
Server-Sent Events
```

or WebSocket.

Example:

```text
Preparing                 10%
Analyzing speech          25%
Generating captions       35%
Selecting clips           45%
Building timeline         55%
Rendering                 75%
Validating                90%
Uploading                 97%
Completed                100%
```

---

# 35. Output Validation

Never mark a render complete merely because FFmpeg exited successfully.

Validate:

```text
file exists
duration ~= expected audio duration
video stream exists
audio stream exists
resolution = 1080x1920
FPS valid
codec valid
file readable
thumbnail generated
```

Duration tolerance can be configured, for example:

```text
±50ms
```

depending on encoding behavior.

---

# 36. Quality Gates

Before publishing a render:

```text
Q1: Audio exists
Q2: Word timestamps exist
Q3: Captions cover speech
Q4: Visual timeline covers full duration
Q5: No invalid source clips
Q6: Output duration matches audio
Q7: Output resolution correct
Q8: Final file playable
```

Only then:

```text
COMPLETED
```

---

# 37. Frontend State Model

Project states:

```text
DRAFT
VOICE_GENERATING
VOICE_READY
RENDER_QUEUED
RENDERING
READY
FAILED
```

The Make Short button is enabled only when:

```text
script valid
AND
audio exists
AND
audio status = READY
```

---

# 38. Main Project UI

```text
┌───────────────────────────────────────────────┐
│ CREATE SHORT                                  │
├───────────────────────────────────────────────┤
│                                               │
│ TITLE                                         │
│ [ The Painting That Predicted The Market ]    │
│                                               │
│ SCRIPT                                        │
│ ┌───────────────────────────────────────────┐ │
│ │ Paste your story here...                  │ │
│ │                                           │ │
│ └───────────────────────────────────────────┘ │
│                                               │
│ VOICE                                         │
│ [ Voice ▼ ] [ Speed ] [ Generate Voice ]      │
│                                               │
│ AUDIO                                         │
│ ▶ ─────────────────────────────────────       │
│                                               │
│             [ MAKE SHORT ]                    │
│                                               │
└───────────────────────────────────────────────┘
```

After rendering:

```text
┌───────────────────────────────────────────────┐
│ SHORT READY                                   │
│                                               │
│              ┌──────────────┐                 │
│              │              │                 │
│              │  9:16 VIDEO  │                 │
│              │              │                 │
│              └──────────────┘                 │
│                                               │
│ [ Download ] [ Regenerate ] [ Edit Template ] │
└───────────────────────────────────────────────┘
```

---

# 39. Template Architecture

Templates must be versioned.

```text
Yellow Story v1
Yellow Story v2
```

Never silently modify an existing template version used by old renders.

Template contains:

```text
canvas
title
caption
font
safe areas
positioning
animations
transition rules
audio configuration
```

---

# 40. Default Yellow Story Template

```json
{
  "canvas": {
    "width": 1080,
    "height": 1920,
    "fps": 30
  },
  "title": {
    "color": "#FFD400",
    "position": "top",
    "maxLines": 3,
    "fontWeight": 800
  },
  "captions": {
    "color": "#FFD400",
    "position": "bottom-center",
    "maxWords": 5,
    "maxLines": 2,
    "outline": "#000000",
    "outlineWidth": 4
  },
  "audio": {
    "sourceVideoAudio": false
  }
}
```

---

# 41. Project Directory Structure

```text
short-video-platform/
│
├── apps/
│   ├── web/
│   │   ├── app/
│   │   ├── components/
│   │   ├── hooks/
│   │   └── lib/
│   │
│   ├── api/
│   │   ├── routes/
│   │   ├── modules/
│   │   ├── middleware/
│   │   └── server.ts
│   │
│   └── worker/
│       ├── processors/
│       ├── queues/
│       └── worker.ts
│
├── packages/
│   ├── database/
│   ├── types/
│   ├── validation/
│   ├── storage/
│   ├── tts/
│   ├── speech/
│   ├── media/
│   ├── captions/
│   ├── timeline/
│   ├── rendering/
│   └── templates/
│
├── infrastructure/
│   ├── docker/
│   ├── migrations/
│   └── deployment/
│
├── tests/
│   ├── unit/
│   ├── integration/
│   └── e2e/
│
├── docker-compose.yml
├── package.json
└── README.md
```

---

# 42. Testing Strategy

## Unit Tests

Test:

```text
caption segmentation
clip selection
duration calculations
timeline construction
template validation
render configuration
```

## Integration Tests

Test:

```text
TTS → storage
storage → alignment
media → FFprobe
timeline → FFmpeg
render → storage
```

## End-to-End Test

One complete scenario:

```text
Create project
 ↓
Generate voice
 ↓
Click Make Short
 ↓
Render
 ↓
Validate MP4
 ↓
Preview
```

---

# 43. Example End-to-End Render

Input:

```text
Script:
"I took the job because I was broke."
```

Generated audio:

```text
4.82 seconds
```

Alignment:

```text
I        0.00 - 0.18
took     0.18 - 0.51
the      0.51 - 0.65
job      0.65 - 0.93
because  0.93 - 1.37
I        1.37 - 1.51
was      1.51 - 1.72
broke    1.72 - 2.31
```

Caption engine:

```text
I TOOK THE JOB
BECAUSE I WAS BROKE
```

B-roll:

```text
clip_12 = 3.4s
clip_27 = 2.1s
```

Final visual duration:

```text
5.5s → trim to 4.82s
```

Final output:

```text
1080x1920
4.82s
Voice = generated narration
Clip audio = muted
Title = yellow
Captions = yellow + synchronized
```

---

# 44. Performance Architecture

The API must remain stateless.

```text
Load Balancer
      ↓
API 1
API 2
API 3
```

Workers scale independently:

```text
Render Worker × N
Alignment Worker × N
TTS Worker × N
```

Only shared infrastructure contains state:

```text
PostgreSQL
Redis
Object Storage
```

---

# 45. Caching

Cache:

```text
template configuration
font metadata
media metadata
frequently requested project metadata
```

Do not cache mutable render state incorrectly.

Audio/TTS caching can be keyed by:

```text
hash(script + voice + settings)
```

This can prevent unnecessary TTS regeneration.

---

# 46. Cost Control

Expensive operations:

```text
TTS
Speech alignment
FFmpeg rendering
Object storage
Bandwidth
```

Track per project:

```text
ttsCost
renderCpuSeconds
storageBytes
outputBandwidth
```

Later this enables:

```text
free tier
credits
subscriptions
usage limits
```

---

# 47. Production Deployment

Recommended initial deployment:

```text
Frontend:
Vercel / equivalent

API:
Docker container

Workers:
Docker containers

Database:
Managed PostgreSQL

Redis:
Managed Redis

Storage:
S3 / R2

Monitoring:
Sentry + metrics platform
```

For heavier rendering workloads:

```text
Dedicated worker machines
GPU optional later
Autoscaling
```

FFmpeg rendering does not require a GPU for the basic pipeline.

---

# 48. CI/CD

Every pull request:

```text
Lint
Typecheck
Unit tests
Build
Integration tests
```

Deployment pipeline:

```text
Git push
 ↓
CI
 ↓
Build Docker images
 ↓
Security scan
 ↓
Deploy API
 ↓
Deploy workers
 ↓
Database migration
 ↓
Smoke test
```

Never automatically run destructive database operations during deployment.

---

# 49. Development Environment

Use Docker Compose:

```text
web
api
worker
postgres
redis
minio
```

MinIO can emulate S3 locally.

Local architecture:

```text
Browser
   ↓
Next.js
   ↓
API
   ├── PostgreSQL
   ├── Redis
   └── MinIO
          ↑
        Worker
          ↑
        FFmpeg
```

---

# 50. MVP Delivery Phases

## Phase 1: Foundation

```text
Auth
Project CRUD
PostgreSQL
Object storage
Media upload
Basic frontend
```

## Phase 2: Voice

```text
TTS abstraction
Voice generation
Audio storage
Audio preview
Voice-ready state
```

## Phase 3: Short Engine

```text
Make Short
Job queue
Speech alignment
Caption engine
Clip selector
Timeline builder
```

## Phase 4: Renderer

```text
FFmpeg
9:16 normalization
Clip concatenation
Voice muxing
Yellow title
Yellow captions
Output validation
```

## Phase 5: Productization

```text
Media library
Templates
Regeneration
Render history
Progress UI
Error handling
```

## Phase 6: Intelligence

```text
Semantic B-roll
AI crop
AI title generation
Better caption segmentation
Scene relevance
```

---

# 51. MVP Acceptance Criteria

The MVP is complete when:

### Input

```text
User can paste a script.
```

### Voice

```text
User can generate voice.
```

### Trigger

```text
Make Short appears when voice is ready.
```

### Video

```text
System automatically selects multiple video assets.
```

### Timeline

```text
Selected videos cover the complete narration.
```

### Captions

```text
Captions follow actual speech timing.
```

### Styling

```text
Title is yellow.
Captions are yellow.
```

### Audio

```text
Generated narration is the final primary audio.
Source clip audio is muted.
```

### Output

```text
1080x1920 MP4
9:16
Playable
Duration matches narration
```

### UX

```text
User does not manually edit the timeline.
```

---

# 52. Critical Engineering Principles

## Principle 1: Audio is authoritative

```text
Audio → duration → captions → visual timeline
```

Never the other way around.

## Principle 2: Rendering is asynchronous

Never render inside an API request.

## Principle 3: Media belongs in object storage

Never store MP4 blobs in PostgreSQL.

## Principle 4: Workers are disposable

A worker can die and the job can be retried.

## Principle 5: Rendering is reproducible

Persist seed + timeline + versions.

## Principle 6: Providers are abstractions

TTS and speech alignment providers must be replaceable.

## Principle 7: Templates are versioned

Old renders must remain reproducible.

## Principle 8: Validation happens after rendering

A successful FFmpeg exit is not sufficient.

---

# 53. Final Architecture

```text
                             USER
                              │
                              ▼
                     ┌─────────────────┐
                     │  NEXT.JS WEB UI │
                     └────────┬────────┘
                              │
                              ▼
                     ┌─────────────────┐
                     │ API / BFF       │
                     │ TypeScript      │
                     └───┬─────┬───────┘
                         │     │
             ┌───────────┘     └─────────────┐
             ▼                               ▼
      ┌──────────────┐                ┌──────────────┐
      │ PostgreSQL   │                │ Object Store │
      │ Project Data │                │ Media        │
      └──────────────┘                └──────────────┘
                         │
                         ▼
                  ┌──────────────┐
                  │ Redis/BullMQ │
                  └──────┬───────┘
                         │
          ┌──────────────┼────────────────┐
          ▼              ▼                ▼
     ┌────────┐    ┌────────────┐   ┌────────────┐
     │ TTS    │    │ Alignment  │   │ Media      │
     │ Worker │    │ Worker     │   │ Worker     │
     └────────┘    └────────────┘   └────────────┘
                         │
                         ▼
                  ┌──────────────┐
                  │ Timeline     │
                  │ Builder      │
                  └──────┬───────┘
                         │
                         ▼
                  ┌──────────────┐
                  │ Render Queue │
                  └──────┬───────┘
                         │
                         ▼
                  ┌──────────────┐
                  │ FFmpeg       │
                  │ Render Pool  │
                  └──────┬───────┘
                         │
             ┌───────────┴───────────┐
             ▼                       ▼
       ┌────────────┐         ┌────────────┐
       │ Final MP4  │         │ Thumbnail  │
       └─────┬──────┘         └─────┬──────┘
             │                      │
             └──────────┬───────────┘
                        ▼
                 ┌─────────────┐
                 │ Object Store│
                 └──────┬──────┘
                        │
                        ▼
                    USER PREVIEW
```

---

# 54. The Core Product Contract

The entire platform can ultimately be reduced to this contract:

```text
INPUT
─────
Script
Voice
Video Library
Title
Template

PROCESS
───────
Speech Alignment
+
Caption Generation
+
Clip Selection
+
Timeline Construction
+
FFmpeg Rendering

OUTPUT
──────
A production-ready 9:16 short

with:

✓ narration
✓ randomized/relevant B-roll
✓ yellow headline
✓ real-time yellow captions
✓ synchronized timing
✓ muted source-video audio
✓ validated MP4
```

The architecture should be implemented as a **modular monolith first**, with clear service interfaces and queue boundaries. Split services only when scale or deployment requirements justify it. This avoids the classic engineering ritual of creating seventeen microservices before the application has managed to render one video.
