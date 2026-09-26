# Auto Script Generation & Multi-Layer Pipeline

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                        LAYER 5: ORCHESTRATOR                       │
│  Batch queue, scheduling, retry logic, status tracking, API        │
├─────────────────────────────────────────────────────────────────────┤
│                        LAYER 4: SCRIPT GENERATOR                   │
│  LLM-powered script writing with hooks, pacing, retention tactics  │
├─────────────────────────────────────────────────────────────────────┤
│                        LAYER 3: CONTENT STRATEGY                   │
│  Niche selection, topic clustering, trend scoring, content calendar│
├─────────────────────────────────────────────────────────────────────┤
│                        LAYER 2: PRODUCTION ENGINE                  │
│  TTS generation, voice selection, tone mapping, caption timing     │
├─────────────────────────────────────────────────────────────────────┤
│                        LAYER 1: RENDER & DELIVERY                  │
│  FFmpeg render, export, upload queue, analytics feedback loop      │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Layer 1: Content Strategy Engine

### Purpose
Determine WHAT to write about, WHEN to post, and WHO the audience is.

### Data Structures

```python
# backend/app/services/auto_gen/strategy.py

@dataclass
class NicheConfig:
    name: str                          # e.g. "true_crime", "tech_tips", "psychology"
    keywords: list[str]                # seed keywords for topic discovery
    audience_age: tuple[int, int]      # (18, 34)
    audience_interests: list[str]      # ["mystery", "self_improvement"]
    hook_style: str                    # "question", "shocking_fact", "story", "listicle"
    optimal_duration: tuple[int, int]  # (30, 59) seconds
    posting_schedule: list[str]        # ["mon_wed_fri", "daily"]
    voice_preference: str              # "am_adam"
    tone_preference: str               # "deep"
    preset_preference: str             # "shorts"

@dataclass
class TopicCluster:
    id: str
    niche: str
    title_seed: str
    subtopics: list[str]
    trend_score: float                 # 0.0 - 1.0
    competition_score: float           # 0.0 - 1.0 (lower = easier to rank)
    evergreen: bool
    related_topics: list[str]
    estimated_ctr: float               # predicted click-through rate

@dataclass
class ContentCalendar:
    schedule: list[CalendarEntry]

@dataclass
class CalendarEntry:
    date: str                          # "2026-08-15"
    time: str                          # "14:00"
    niche: str
    topic: TopicCluster
    script_type: str                   # "hook", "story", "listicle", "debate"
    status: str                        # "queued", "generating", "done", "failed"
```

### Topic Discovery Methods

| Method | Source | Priority |
|--------|--------|----------|
| Keyword expansion | Seed keywords + LLM synonyms | High |
| Trend scraping | Google Trends, Reddit, X/Twitter | Medium |
| Competitor analysis | Top channels in niche | Medium |
| Evergreen bank | Pre-written topic database | High |
| User prompts | Manual topic injection | Low |

### Trend Scoring Algorithm

```
trend_score = (
    search_volume_normalized * 0.3 +
    social_mentions_normalized * 0.25 +
    recency_decay * 0.25 +
    niche_relevance * 0.2
)

competition_score = (
    existing_shorts_count * 0.4 +
    avg_view_count * 0.3 +
    channel_size_avg * 0.3
)

priority = trend_score * (1.0 - competition_score)
```

---

## Layer 2: Script Generator Engine

### Purpose
Turn a topic into a spoken-word script optimized for YouTube Shorts retention.

### Script Types

| Type | Structure | Hook | Body | Close |
|------|-----------|------|------|-------|
| **hook_story** | Hook -> Story -> Payoff | Shocking question/statement | 2-3 sentence narrative | Twist or answer |
| **listicle** | Hook -> 3 items -> CTA | "3 things you didn't know..." | Each item with punch | "Follow for more" |
| **debate** | Hook -> Side A -> Side B -> Verdict | Controversial take | Present both sides | Hot take conclusion |
| **fact_bomb** | Hook -> Fact -> Why it matters | Mind-blowing stat | Simple explanation | "Think about that" |
| **story_time** | Hook -> Rising action -> Climax -> Resolution | "This is insane..." | Build tension | Satisfying end |
| **how_to** | Problem -> Steps -> Result | "You're doing X wrong" | 2-3 quick steps | Before/after payoff |

### Script Constraints (YouTube Shorts)

```
MAX_DURATION: 59 seconds
OPTIMAL_DURATION: (35, 55) seconds
MAX_WORDS: 140
OPTIMAL_WORDS: (80, 130)
MIN_WORDS: 40
WORDS_PER_SECOND: 2.3 - 2.5 (natural speaking pace)
```

### Script Structure Template

```python
@dataclass
class GeneratedScript:
    id: str
    topic: TopicCluster
    script_type: str
    hook: str                          # First 1-2 sentences (CRITICAL)
    body: str                          # Main content
    close: str                         # Final sentence (CTA or payoff)
    full_text: str                     # hook + body + close joined
    word_count: int
    estimated_duration: float          # seconds
    target_emotion: str                # primary emotion to evoke
    retention_tactics: list[str]       # ["open_loop", "pattern_interrupt", ...]
    metadata: dict                     # niche, topic_id, generation params
```

### Hook Formulas (12 proven patterns)

```python
HOOK_PATTERNS = {
    "open_loop": "Nobody talks about {topic} but here's why it matters.",
    "shocking_stat": "{percentage}% of people don't know this about {topic}.",
    "controversial": "Unpopular opinion: {hot_take}.",
    "story_start": "This is the story of {subject} and it changes everything.",
    "question": "Have you ever wondered why {question}?",
    "challenge": "You think you know {topic}? Think again.",
    "secret": "There's a secret about {topic} that nobody tells you.",
    "mistake": "Stop making this mistake with {topic} right now.",
    "comparison": "{A} vs {B} and the answer will surprise you.",
    "timeline": "In exactly {timeframe}, everything about {topic} changed.",
    "confession": "I can't believe this but {confession}.",
    "warning": "If you're into {topic}, you need to hear this.",
}
```

### Retention Tactics

| Tactic | Where | Effect |
|--------|-------|--------|
| Open loop | Hook | Creates curiosity gap |
| Pattern interrupt | Every 8-10 seconds | Prevents scroll-away |
| Name dropping | Body | Personal connection |
| Rhetorical question | Body | Engages thinking |
| Callback | Close | Satisfying resolution |
| Cliffhanger word | End of phrase | Pulls to next sentence |
| Contrast | Body | "Most people think X, but Y" |
| Specificity | Anywhere | "3.7 seconds" > "a few seconds" |

### LLM Integration

```python
# backend/app/services/auto_gen/script_generator.py

SYSTEM_PROMPT = """
You write spoken-word scripts for YouTube Shorts (vertical, <60s).
The script will be narrated by AI voice, not shown as text on screen.

RULES:
- Write in conversational spoken English, not formal writing
- Short sentences. Max 15 words per sentence.
- No complex vocabulary. Grade 6-8 reading level.
- Vary sentence length: 5 words, then 12, then 7, then 14.
- Start strong. First 3 words decide if viewer stays.
- End strong. Last sentence is the payoff or CTA.
- No throat-clearing: "So basically", "In today's video", "Hey guys"
- Direct address: "you", "your" -- not "one" or "people"
- One idea per sentence. No compound sentences with "and" or "but".
- Use concrete words. "34 million" not "a lot".

SCRIPT TYPE: {script_type}
NICHE: {niche}
TOPIC: {topic}
HOOK STYLE: {hook_style}
TARGET DURATION: {target_seconds} seconds (~{target_words} words)
TARGET EMOTION: {target_emotion}
"""

USER_PROMPT = """
Write a {script_type} YouTube Short script about: {topic}
Target: {target_words} words, {target_seconds} seconds.
Hook style: {hook_style}
Emotion: {target_emotion}
Niche: {niche}
"""

# Response format: JSON with hook, body, close fields
RESPONSE_SCHEMA = {
    "hook": "str - First 1-2 sentences",
    "body": "str - Main content",
    "close": "str - Final sentence",
    "retention_tactics": ["list of tactics used"],
    "estimated_duration": "float"
}
```

### Quality Validation

```python
def validate_script(script: GeneratedScript) -> list[ValidationResult]:
    checks = [
        ("word_count", script.word_count, 40, 140),
        ("duration", script.estimated_duration, 30, 59),
        ("hook_length", word_count(script.hook), 3, 30),
        ("no_filler", not contains_filler(script.full_text)),
        ("no_formal", not contains_formal(script.full_text)),
        ("sentence_length", max_sentence_words(script.full_text), 3, 18),
        ("varied_length", sentence_length_variance(script.full_text) > 0.3),
        ("starts_strong", hook_start_quality(script.hook)),
        ("ends_strong", close_quality(script.close)),
        ("emotion_match", emotion_consistency(script)),
    ]
    return [r for r in checks if not r.passed]
```

---

## Layer 3: Production Engine

### Purpose
Turn scripts into audio with optimal voice/tone settings.

### Voice-Topic Mapping

```python
VOICE_TOPIC_MAP = {
    "true_crime": {"voices": ["am_adam", "am_onyx"], "tone": "deep", "speed": 0.95},
    "tech_tips":  {"voices": ["am_michael", "bm_lewis"], "tone": "crisp", "speed": 1.05},
    "psychology": {"voices": ["am_liam", "af_heart"], "tone": "warm", "speed": 1.0},
    "finance":    {"voices": ["am_adam", "bm_george"], "tone": "deep", "speed": 0.98},
    "science":    {"voices": ["am_fenrir", "af_sarah"], "tone": "natural", "speed": 1.0},
    "horror":     {"voices": ["am_onyx", "af_nicole"], "tone": "dark", "speed": 0.90},
    "comedy":     {"voices": ["am_liam", "af_nova"], "tone": "bright", "speed": 1.08},
    "motivation": {"voices": ["am_fenrir", "af_bella"], "tone": "resonant", "speed": 1.02},
}
```

### Production Pipeline

```
Script (text)
    │
    ├─► Voice selection (niche-based or random from preferred list)
    ├─► Tone selection (from VOICE_TOPIC_MAP or override)
    ├─► Speed calculation (word_count / target_duration)
    │
    ▼
TTS Generation
    │
    ├─► Audio quality check (duration matches? no artifacts?)
    ├─► Word-level timestamp extraction (whisper)
    │
    ▼
Caption Generation
    │
    ├─► Word grouping (2-3 words per cue)
    ├─► Timing sync with audio
    │
    ▼
Render Input Package (audio + captions + metadata)
```

---

## Layer 4: Orchestrator

### Purpose
Coordinate the full pipeline from topic to final video. Handle batching, retries, and status.

### Batch Job Model

```python
@dataclass
class BatchJob:
    id: str
    name: str                          # "daily_crime_batch_2026_08_15"
    status: str                        # "pending", "running", "completed", "failed"
    config: BatchConfig
    scripts: list[GeneratedScript]
    outputs: list[RenderOutput]
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
    error_log: list[str]

@dataclass
class BatchConfig:
    count: int                         # how many videos to produce
    niches: list[str]                  # which niches to pull topics from
    script_types: list[str]            # ["hook_story", "listicle", ...]
    voice_override: str | None         # force specific voice
    tone_override: str | None          # force specific tone
    priority: str                      # "trend_first", "evergreen_first", "mixed"
    max_retries: int                   # 3
    auto_render: bool                  # True = also render to MP4
    auto_cleanup: bool                 # True = delete intermediate files
```

### Pipeline Steps

```
1. PLAN
   ├─ Select topics from content strategy
   ├─ Assign script types per topic
   ├─ Create BatchJob with N items
   └─ Queue for generation

2. GENERATE
   ├─ For each script in batch:
   │   ├─ Call LLM with topic + type + constraints
   │   ├─ Validate script quality
   │   ├─ Retry on validation failure (max 3)
   │   ├─ Store script in DB
   │   └─ Update progress
   └─ Mark batch as "scripts_done"

3. PRODUCE
   ├─ For each script in batch:
   │   ├─ Select voice + tone from mapping
   │   ├─ Generate TTS audio
   │   ├─ Extract word timestamps
   │   ├─ Generate captions
   │   ├─ Quality check (duration match, no silence gaps)
   │   └─ Update progress
   └─ Mark batch as "audio_done"

4. RENDER
   ├─ For each audio in batch:
   │   ├─ Select B-roll clips
   │   ├─ Render MP4 via FFmpeg
   │   ├─ Generate thumbnail
   │   ├─ Validate output
   │   └─ Update progress
   └─ Mark batch as "completed"

5. DELIVER
   ├─ List completed renders
   ├─ Download all as ZIP (optional)
   ├─ Track analytics per video
   └─ Feed performance data back to strategy layer
```

### Status Tracking

```python
class JobStatus:
    PENDING     = "pending"
    GENERATING  = "generating"
    SCRIPT_DONE = "script_done"
    PRODUCING   = "producing"
    AUDIO_DONE  = "audio_done"
    RENDERING   = "rendering"
    COMPLETED   = "completed"
    FAILED      = "failed"
    RETRYING    = "retrying"
```

### API Endpoints (New)

```
POST   /api/auto/batch              Create a batch job
GET    /api/auto/batch/{id}         Get batch status
GET    /api/auto/batches            List all batches
DELETE /api/auto/batch/{id}         Cancel/delete batch
POST   /api/auto/batch/{id}/retry   Retry failed items
GET    /api/auto/batch/{id}/scripts List generated scripts
GET    /api/auto/batch/{id}/outputs List rendered outputs
POST   /api/auto/generate-script    Generate single script (no batch)
POST   /api/auto/topics             Get suggested topics for niche
GET    /api/auto/niches             List available niches
POST   /api/auto/calendar           Generate content calendar
```

---

## Layer 5: Delivery & Feedback

### Export Options

| Method | Description |
|--------|-------------|
| ZIP download | All MP4s + thumbnails in one archive |
| Individual download | Single video click |
| Folder output | Save to specific directory |
| Upload queue | Queue for YouTube/social upload (future) |

### Analytics Feedback Loop

```
Video Published
    │
    ├─► Track: views, watch_time, retention_curve, likes, comments
    ├─► After 48h: calculate performance_score
    │
    ▼
Strategy Update
    ├─► High performing topic? Increase frequency.
    ├─► High performing hook style? Use more.
    ├─► Low retention at 5s? Review hook formulas.
    ├─► Low retention at 30s? Review body pacing.
    └─► Feed scores back into trend_score algorithm
```

---

## Database Schema Additions

```sql
-- Niches
CREATE TABLE niches (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    keywords JSON,
    voice_preference TEXT,
    tone_preference TEXT,
    is_active BOOLEAN DEFAULT 1,
    created_at TIMESTAMP
);

-- Topics
CREATE TABLE topics (
    id TEXT PRIMARY KEY,
    niche_id TEXT REFERENCES niches(id),
    title TEXT NOT NULL,
    subtopics JSON,
    trend_score FLOAT,
    competition_score FLOAT,
    evergreen BOOLEAN,
    times_used INTEGER DEFAULT 0,
    last_used_at TIMESTAMP,
    created_at TIMESTAMP
);

-- Generated Scripts
CREATE TABLE generated_scripts (
    id TEXT PRIMARY KEY,
    batch_id TEXT,
    topic_id TEXT REFERENCES topics(id),
    script_type TEXT NOT NULL,
    hook TEXT,
    body TEXT,
    close TEXT,
    full_text TEXT,
    word_count INTEGER,
    estimated_duration FLOAT,
    target_emotion TEXT,
    retention_tactics JSON,
    quality_score FLOAT,
    status TEXT DEFAULT 'pending',
    created_at TIMESTAMP
);

-- Batch Jobs
CREATE TABLE batch_jobs (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    config JSON,
    status TEXT DEFAULT 'pending',
    total_items INTEGER,
    completed_items INTEGER,
    failed_items INTEGER,
    created_at TIMESTAMP,
    started_at TIMESTAMP,
    completed_at TIMESTAMP
);

-- Content Calendar
CREATE TABLE content_calendar (
    id TEXT PRIMARY KEY,
    scheduled_date DATE,
    scheduled_time TIME,
    niche_id TEXT REFERENCES niches(id),
    topic_id TEXT REFERENCES topics(id),
    script_id TEXT REFERENCES generated_scripts(id),
    status TEXT DEFAULT 'queued',
    created_at TIMESTAMP
);

-- Performance Analytics
CREATE TABLE video_analytics (
    id TEXT PRIMARY KEY,
    render_output_id TEXT,
    script_id TEXT,
    topic_id TEXT,
    views INTEGER DEFAULT 0,
    watch_time_seconds FLOAT DEFAULT 0,
    retention_curve JSON,
    likes INTEGER DEFAULT 0,
    comments INTEGER DEFAULT 0,
    shares INTEGER DEFAULT 0,
    performance_score FLOAT,
    measured_at TIMESTAMP
);
```

---

## File Structure (New)

```
backend/app/services/auto_gen/
├── __init__.py
├── strategy.py           # NicheConfig, TopicCluster, trend scoring
├── topic_bank.py         # Pre-defined evergreen topics per niche
├── script_generator.py   # LLM script generation + validation
├── hook_library.py       # Hook formulas and patterns
├── retention_optimizer.py # Script quality scoring
├── producer.py           # Voice/tone selection, TTS orchestration
├── orchestrator.py       # Batch job management, pipeline coordination
├── calendar.py           # Content scheduling logic
├── feedback.py           # Analytics ingestion, strategy updates

backend/app/api/auto_gen.py  # New API router for automation endpoints

frontend/src/components/
├── AutoGenPanel.tsx      # Main automation control panel
├── NicheSelector.tsx     # Niche picker
├── TopicBrowser.tsx      # Topic suggestions + search
├── ScriptPreview.tsx     # Generated script preview + edit
├── BatchDashboard.tsx    # Batch job progress + management
├── ContentCalendar.tsx   # Calendar view of scheduled content
├── ScriptEditor.tsx      # (existing) add "auto-generate" button
```

---

## Implementation Phases

### Phase 1: Foundation (Week 1)
- [ ] Create `auto_gen/` service directory
- [ ] Implement `strategy.py` with NicheConfig
- [ ] Build `topic_bank.py` with 50+ evergreen topics per niche
- [ ] Add niches/topics DB tables
- [ ] API: `GET /api/auto/niches`, `POST /api/auto/topics`

### Phase 2: Script Engine (Week 2)
- [ ] Implement `script_generator.py` with LLM integration
- [ ] Build `hook_library.py` with all 12 hook patterns
- [ ] Implement `retention_optimizer.py` quality scoring
- [ ] Add validation pipeline (word count, duration, filler check)
- [ ] API: `POST /api/auto/generate-script`

### Phase 3: Batch Pipeline (Week 3)
- [ ] Implement `orchestrator.py` batch job manager
- [ ] Add batch_jobs, generated_scripts DB tables
- [ ] Wire script generator -> TTS -> render pipeline
- [ ] Add retry logic with exponential backoff
- [ ] API: `POST /api/auto/batch`, `GET /api/auto/batch/{id}`

### Phase 4: Frontend (Week 4)
- [ ] Build `AutoGenPanel.tsx` with niche/topic selection
- [ ] Build `ScriptPreview.tsx` for script review + regeneration
- [ ] Build `BatchDashboard.tsx` with live progress
- [ ] Add "Auto-Generate" button to ScriptEditor
- [ ] Build batch job list + detail views

### Phase 5: Feedback Loop (Week 5)
- [ ] Add video_analytics DB table
- [ ] Implement `feedback.py` analytics ingestion
- [ ] Feed performance scores back into topic/trend scoring
- [ ] Build analytics dashboard in frontend
- [ ] Auto-adjust posting frequency based on performance

---

## Example Flow: End-to-End

```
User selects: Niche = "true_crime", Count = 5, Auto-render = ON

1. STRATEGY
   └─► Pulls 5 topics from topic_bank (evergreen + trend-boosted):
       - "The disappearances that shook a small town"
       - "Why this cold case was solved by accident"
       - "The one clue everyone missed"
       - "What detectives found changed everything"
       - "This evidence was hidden in plain sight"

2. SCRIPT GENERATION
   └─► For each topic, LLM generates:
       - hook_story script, ~110 words, ~48 seconds
       - Deep tone, serious emotion
       - Open loop + specificity retention tactics

3. PRODUCTION
   └─► For each script:
       - Voice: am_adam (from VOICE_TOPIC_MAP.true_crime)
       - Tone: deep
       - Speed: calculated from word_count / target_duration
       - TTS audio generated
       - Word timestamps extracted
       - Captions synced

4. RENDER
   └─► For each audio:
       - B-roll: random from videotemplate/
       - Title overlay: topic title
       - Captions: yellow, bottom-third
       - Output: 1080x1920 MP4

5. DELIVER
   └─► 5 MP4s ready for download
       - ZIP archive available
       - Scripts saved for re-generation
       - Topic marked as "used" in DB
```
