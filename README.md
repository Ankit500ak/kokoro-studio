<div align="center">

# Kokoro Studio

**Turn a script into a finished, narrated, captioned video — entirely on your own machine.**

Local-first AI voice & video studio: Kokoro TTS, an LLM story pipeline, FFmpeg rendering,
a Telegram auto-pilot and one-click YouTube upload.

[![Visibility](https://img.shields.io/badge/visibility-public-brightgreen?style=flat-square)](https://github.com/Ankit500ak/kokoro-studio)
[![Repo size](https://img.shields.io/github/repo-size/Ankit500ak/kokoro-studio?style=flat-square)](https://github.com/Ankit500ak/kokoro-studio)
[![Last commit](https://img.shields.io/github/last-commit/Ankit500ak/kokoro-studio?style=flat-square)](https://github.com/Ankit500ak/kokoro-studio)
[![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?style=flat-square&logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-009688?style=flat-square&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![React](https://img.shields.io/badge/React-18-61DAFB?style=flat-square&logo=react&logoColor=black)](https://react.dev/)
[![Vite](https://img.shields.io/badge/Vite-5-646CFF?style=flat-square&logo=vite&logoColor=white)](https://vitejs.dev/)
[![Windows](https://img.shields.io/badge/platform-Windows-0078D6?style=flat-square&logo=windows&logoColor=white)](https://github.com/Ankit500ak/kokoro-studio)

[Features](#features) · [Architecture](#architecture) · [Quick start](#quick-start) · [Configuration](#configuration) · [API](#api-surface) · [Large data](#large-data--not-in-this-repo) · [Docs](#documentation)

</div>

---

## Overview

Kokoro Studio is a full content pipeline, not just a TTS toy:

**write the script → generate the voiceover → pick stock footage → burn captions → render → upload to YouTube.**

Everything runs locally except the optional LLM script generation and the final YouTube
upload. No cloud TTS, no subscription, no watermarks — your audio, renders and library
live in one folder on your disk.

| Area | What you get |
|---|---|
| **Voice** | 14 Kokoro voices (7 male / 7 female) with per-voice speed, weight and emotion tuning |
| **Script** | Story Forge writes hooks, drafts, retention passes and quality scores (Google Gemini) |
| **Video** | Media library + templates + clip selector, rendered through FFmpeg with burned-in captions |
| **Publish** | YouTube OAuth upload with metadata/thumbnail generation, or drive the whole thing from Telegram |

---

## Features

**Text-to-speech engine**
- Kokoro-82M pipelines with chunked generation and timeout control for long scripts
- Emphasis, prosody and pause control (ALL CAPS, punctuation cues) without post-processing
- Voice previews, tuning profiles per voice, tone presets
- Persistent audio library with waveform playback in the UI

**Story Forge (LLM script pipeline)**
- Hook selection → draft generation → retention pass → quality score, as resumable steps
- Theme tracker + "used themes" log so videos don't repeat themselves
- Google Gemini (`GEMINI_API_KEY`) - the sole AI provider for scripts, metadata and story refinement

**Video pipeline**
- Media library: upload or scan your own footage, folder-based, thumbnails included
- Templates with per-template config, clip selector and timeline builder
- Multi-pass generation, speech alignment and ASS caption rendering
- Async render jobs with progress polling, retry, thumbnails and download

**Publishing**
- YouTube Data API upload (OAuth, tokens encrypted at rest with Fernet)
- Auto-generated metadata (title/description/tags) and thumbnails
- Upload history, queue and playlist selection

**Automation**
- Telegram bot: send it a prompt, it runs script → TTS → render → upload
- Windows `.bat` launchers for backend, frontend, bot or all three at once

---

## Architecture

```
 ┌───────────────────────┐  /api (JSON, proxied)  ┌───────────────────────────────────────┐
 │  Frontend (React)     │ ─────────────────────► │  Backend (FastAPI)        :8000      │
 │  Vite dev server      │                        │                                       │
 │  :5174                │                        │  /api/tts          Kokoro TTS         │
 └───────────────────────┘                        │  /api/story_forge  Gemini             │
                                                  │  /api/media        library + upload   │
 ┌───────────────────────┐                        │  /api/renders      FFmpeg jobs        │
 │  Telegram bot         │ ─────────────────────► │  /api/templates    templates          │
 │  telegram_bot.py      │                        │  /api/projects     project CRUD       │
 └───────────────────────┘                        │  /api/library      generated audio    │
                                                  │  /api/youtube      OAuth + upload     │
                                                  └──────────────┬────────────────────────┘
                                                                 │
                       ┌─────────────────────────────────────────┼──────────────────────┐
                       │  backend/app/storage/ (gitignored)      │                      │
                       ├───────────────┬──────────────┬──────────┴────┬─────────────────┤
                       │ media/        │ audio/       │ renders/      │ kokoro.db       │
                       │ your footage  │ TTS output   │ final videos  │ SQLite (state)  │
                       │ (7 GB)        │ (1.7 GB)     │ (35 GB)       │                 │
                       └───────────────┴──────────────┴───────────────┴─────────────────┘
```

**Stack**

| Layer | Technology |
|---|---|
| Backend | Python, FastAPI, Uvicorn, SQLAlchemy, SQLite (aiosqlite) |
| TTS | [Kokoro](https://github.com/hexgrad/kokoro) (`kokoro` package), soundfile, torch |
| LLM | Google Gemini API (AI Studio, OpenAI-compatible endpoint) |
| Media | FFmpeg (render), Pillow (thumbnails), custom ASS caption engine |
| Frontend | React 18, TypeScript, Vite, Tailwind CSS, Zustand, wavesurfer.js |
| Bot | python-telegram-bot 22 (long-poll worker: `telegram_bot.py`) |
| Secrets | `.env` (never committed) + Fernet encryption for stored OAuth tokens |

---

## Quick start

**Prerequisites:** Windows · Python 3.10+ · Node.js 18+ · [FFmpeg](https://ffmpeg.org/download.html) on `PATH`

```bat
git clone https://github.com/Ankit500ak/kokoro-studio.git
cd kokoro-studio

REM 1. install backend venv + npm dependencies
setup.bat

REM 2. configure secrets
copy backend\.env.example backend\.env
notepad backend\.env

REM 3. run (backend + frontend + telegram bot, each in its own window)
start.bat
```

Then open **http://localhost:5174**.

| Service | Address | Started by |
|---|---|---|
| Web UI | http://localhost:5174 | `start-frontend.bat` |
| API + docs | http://localhost:8000/api/docs | `start-backend.bat` |
| Telegram bot | — | `telegram.bat` |
| All of the above | — | `start.bat` |
| Backend only (PowerShell) | — | `start.ps1` |

> **First synthesis** downloads the Kokoro weights (~0.5 GB) from Hugging Face into your
> local cache. It's a one-time cost — the first generation is slow, the rest are fast.

---

## Configuration

`backend/.env` is the only file you edit. Copy it from `backend/.env.example`.

| Key | Required for | Notes |
|---|---|---|
| `GEMINI_API_KEY` | All AI generation (Story Forge, metadata, /think) | Get one at <https://aistudio.google.com/apikey> |
| `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` | Telegram auto-pilot | @BotFather / @userinfobot |
| `YOUTUBE_CLIENT_ID`, `YOUTUBE_CLIENT_SECRET` | YouTube upload | Google Cloud Console, YouTube Data API v3 |
| `ENCRYPTION_KEY` | Surviving YouTube re-auth across restarts | generate: see comment in `.env.example` |
| `DEFAULT_VOICE`, `DEFAULT_SPEED` | TTS defaults | e.g. `am_liam`, `1.08` |
| `TTS_*_TIMEOUT*` | Slow/CPU machines | raise these if long scripts time out |
| `AUTO_UPLOAD_YOUTUBE` | Automatic upload of finished renders | `false` by default — see *Automatic YouTube upload* below |

Everything else has working defaults. **`.env` is gitignored — never commit it.**

### Automatic YouTube upload (opt-in)

With `AUTO_UPLOAD_YOUTUBE=true`, every render that finishes is uploaded to
YouTube on its own — no manual `POST /api/youtube/upload`. Behaviour:

- **Private by default.** `UPLOAD_PRIVACY_STATUS` defaults to `private`;
  review the video in YouTube Studio, then publish. Switch to `unlisted`
  or `public` only if you really want hands-off publishing.
- **Non-blocking and idempotent.** The upload runs on a background thread
  after the render completes, and a render is never marked failed because
  an upload failed. Each attempt is recorded in the `youtube_uploads`
  table (the same records the manual flow creates), and a render that
  already has a YouTube video id is never uploaded twice.
- **Metadata** comes from the project (title, script excerpt) merged with
  `UPLOAD_TAGS`; the category comes from `UPLOAD_CATEGORY_ID` (default
  `22`). Transient errors are retried up to 3 times with exponential
  backoff; quota and permission errors are not retried.
- **Notification.** With `UPLOAD_NOTIFY_TELEGRAM=true` (and the Telegram
  bot token/chat configured), you get the video URL — or the error —
  after each auto-upload.

One-time setup:

1. In the [Google Cloud Console](https://console.cloud.google.com/),
   create a project and enable the **YouTube Data API v3**.
2. Create an OAuth client and put its id/secret in `YOUTUBE_CLIENT_ID` /
   `YOUTUBE_CLIENT_SECRET`. Keep `YOUTUBE_SCOPES` as in `.env.example` —
   it must include `https://www.googleapis.com/auth/youtube.upload`
   (the `youtube` and `youtube.force-ssl` scopes are needed for
   thumbnails and playlists).
3. Set a stable `ENCRYPTION_KEY` (see `.env.example`) so the stored
   tokens survive restarts.
4. Start the backend and visit `http://localhost:8000/api/youtube/auth`
   once to connect the channel. Tokens are stored Fernet-encrypted.
5. Set `AUTO_UPLOAD_YOUTUBE=true` and restart. Finished renders now
   upload automatically.

---

## API surface

Base URL `http://localhost:8000` · interactive docs at `/api/docs`

| Group | Prefix | Endpoints |
|---|---|---|
| TTS | `/api/tts` | `POST /generate`, `POST /preview`, `POST /analyze`, `GET /voices`, `GET /tone-presets`, `GET /tuning/{voice}` |
| Story Forge | `/api/story_forge` | `POST /start`, `POST /generate-draft/{id}`, `POST /retention-pass/{id}`, `POST /quality-score/{id}`, `POST /run-all` |
| Media | `/api/media` | `GET /`, `GET /folders`, `POST /upload`, `POST /scan`, `GET /{id}/thumbnail` |
| Renders | `/api/renders` | `POST /`, `GET /{job}`, `GET /{job}/file`, `POST /{job}/retry` |
| Templates | `/api/templates` | CRUD + `GET /defaults` |
| Projects | `/api/projects` | CRUD |
| Library | `/api/library` | `GET /`, `GET /stats`, `GET /{id}/file`, `DELETE /{id}` |
| YouTube | `/api/youtube` | `GET /auth`, `GET /callback`, `POST /upload`, `POST /thumbnail/generate`, `GET /uploads`, `GET /queue` |

---

## Project structure

```
kokoro-studio/
├── backend/
│   ├── app/
│   │   ├── api/            FastAPI routers (tts, media, renders, story_forge, youtube…)
│   │   ├── core/           settings, database models, encryption, voices.json
│   │   ├── schemas/        Pydantic request/response models
│   │   ├── services/       kokoro_service, render_service, caption_manager, gemini_client…
│   │   ├── main.py         app entrypoint, logging, lifespan
│   │   └── storage/        RUNTIME DATA — 44 GB, gitignored
│   ├── data/               channel description, upload queue
│   ├── telegram_bot.py     auto-pilot bot
│   ├── requirements.txt
│   └── .env.example
├── frontend/
│   ├── src/components/     28 React components (studio UI)
│   ├── src/lib/            typed API clients
│   └── vite.config.ts      port 5174, /api proxy → :8000
├── docs/                   architecture + GitHub/data guides
├── scripts/pack-data.ps1   build GitHub Release assets from local data
├── setup.bat · start.bat · start-backend.bat · start-frontend.bat · telegram.bat
└── .gitignore              keeps 44+ GB of media out of git
```

---

## Large data — not in this repo

Git carries **code only (~1.2 MB)**. All heavy data is excluded on purpose:

| Excluded | Size | Where it comes from |
|---|---|---|
| `backend/app/storage/` | 44 GB | your video library + generated output + SQLite DB |
| `videotemplate/` | 866 MB | template clips |
| `backend/venv/`, `frontend/node_modules/` | ~2 GB | `setup.bat` |
| Model weights | ~0.5 GB | auto-downloaded on first synthesis |
| `backend/.env` | — | copy from `.env.example` |

Regeneratable output (`renders/`, `audio/`) should never be backed up. For the parts that
*matter* — media library, templates, database — see **[docs/GITHUB_SETUP.md](docs/GITHUB_SETUP.md)**
for copy-from-another-machine instructions and the GitHub Release workflow
(`scripts/pack-data.ps1` packages everything into <2 GiB assets).

---

## Documentation

| Doc | What's in it |
|---|---|
| [docs/GITHUB_SETUP.md](docs/GITHUB_SETUP.md) | data restore, release packaging, git workflow, troubleshooting |
| [VOICE_GUIDE.md](VOICE_GUIDE.md) | voice catalogue: tone, style, best use case |
| [DEEP_ARCHITECTURE.md](DEEP_ARCHITECTURE.md) · [professional_architecture.md](professional_architecture.md) | design notes |
| [YOUTUBE_UPLOAD_PLAN.md](YOUTUBE_UPLOAD_PLAN.md) · [AUTO_SCRIPT_PLAN.md](AUTO_SCRIPT_PLAN.md) | feature plans |
| `http://localhost:8000/api/docs` | live interactive API reference |

---

## License

No license has been published yet — all rights reserved by the author. If you want to
open-source contributions, add a `LICENSE` file and update this section.
