# Kokoro Studio

Local-first AI voice & video studio: turn a script into narrated audio, captions and a
finished vertical/long-form video, then upload it to YouTube — all from a web UI or a
Telegram bot.

**Stack:** FastAPI + Kokoro TTS (Python) · React + Vite + Tailwind (TypeScript) · SQLite · Telegram bot

---

## What's inside

| Piece | Where | What it does |
|---|---|---|
| Backend API | `backend/app/` | TTS synthesis, media library, story pipeline, render engine, YouTube upload |
| Frontend | `frontend/` | React SPA (Vite dev server on port **5174**, proxies `/api` → backend) |
| Telegram bot | `backend/telegram_bot.py` | Auto-pilot: script → TTS → render → upload, driven from chat |
| Data & media | `backend/app/storage/` | **Not in git** — 44 GB of renders, TTS audio, video library, SQLite DB |
| Stock footage | `videotemplate/` | **Not in git** — 866 MB of template clips |

### Key backend modules

- `services/kokoro_service.py` — Kokoro TTS pipelines, chunking, emotion/prosody control
- `services/render_service.py` — FFmpeg render pipeline (audio + video + captions)
- `services/story_forge.py` / `api/story_forge.py` — script generation (NVIDIA NIM, Ollama fallback)
- `services/youtube_uploader.py` — OAuth + encrypted token storage + resumable upload
- `services/caption_manager/` — timing, validation, ASS subtitle rendering

---

## Requirements

- **Windows** (all launchers are `.bat`)
- Python **3.10+**
- Node.js **18+** (npm)
- [FFmpeg](https://ffmpeg.org/download.html) on `PATH` (used for rendering)
- ~10 GB free disk for Python deps + TTS models, plus space for media/renders

---

## Quick start

```bat
:: 1. clone
git clone https://github.com/heywinterbell/kokoro-studio.git
cd kokoro-studio

:: 2. install deps (creates backend\venv + runs npm install)
setup.bat

:: 3. configure secrets
copy backend\.env.example backend\.env
::    then edit backend\.env (see table below)

:: 4. run
start.bat
```

| Service | URL |
|---|---|
| Frontend | http://localhost:5174 |
| Backend API | http://localhost:8000 |
| API docs | http://localhost:8000/docs |

Individual launchers: `start-backend.bat`, `start-frontend.bat`, `telegram.bat`,
or `start.ps1` (backend only, PowerShell).

### Required `.env` values

Everything has a safe default. Only these are worth filling in:

| Key | Needed for | Where to get it |
|---|---|---|
| `NVIDIA_API_KEY` | Story Forge / script generation | https://build.nvidia.com/ |
| `OLLAMA_*` | Free local fallback when no NVIDIA key | https://ollama.com |
| `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` | Telegram bot | @BotFather / @userinfobot |
| `YOUTUBE_CLIENT_ID`, `YOUTUBE_CLIENT_SECRET` | YouTube upload | https://console.cloud.google.com/ |
| `ENCRYPTION_KEY` | Persisting YouTube tokens across restarts | generate: see `.env.example` comment |

> **Never commit `backend/.env`.** It is gitignored — keep it that way.

---

## Large files are NOT in this repo

Git only carries the **code** (~1.2 MB). Everything big lives on your disk and is
excluded by `.gitignore`:

| Excluded path | Size | How to (re)create it |
|---|---|---|
| `backend/app/storage/` | 44 GB | Regeneratable outputs + your video library — see [docs/GITHUB_SETUP.md](docs/GITHUB_SETUP.md) |
| `videotemplate/` | 866 MB | Copy back or download from the `data` GitHub Release |
| `backend/venv/`, `frontend/node_modules/` | ~2 GB | `setup.bat` |
| TTS model weights | ~0.5 GB | Auto-downloaded from Hugging Face on first synthesis |
| `backend/.env` | — | `copy backend\.env.example backend\.env` |

Full instructions (restore, package, publish): **[docs/GITHUB_SETUP.md](docs/GITHUB_SETUP.md)**

---

## Project layout

```
kokoro-studio/
├── backend/
│   ├── app/
│   │   ├── api/           # FastAPI routers (tts, media, renders, story_forge, youtube…)
│   │   ├── core/          # config, db models, encryption, voices.json
│   │   ├── schemas/       # Pydantic request/response models
│   │   ├── services/      # TTS, render, captions, YouTube, metadata, etc.
│   │   └── main.py        # app entrypoint
│   ├── data/              # channel description, upload queue (tracked)
│   ├── storage/           # RUNTIME DATA - ignored (44 GB)
│   ├── telegram_bot.py
│   ├── requirements.txt
│   └── .env.example
├── frontend/
│   ├── src/components/    # React UI
│   ├── src/lib/           # API clients
│   └── vite.config.ts     # port 5174, /api proxy → :8000
├── docs/GITHUB_SETUP.md   # data restore + git/release workflow
├── scripts/pack-data.ps1  # build GitHub Release assets from local data
├── setup.bat  start.bat  start-backend.bat  start-frontend.bat  telegram.bat
└── .gitignore
```

---

## Docs

- [docs/GITHUB_SETUP.md](docs/GITHUB_SETUP.md) — getting the large data, git workflow, publishing releases
- `VOICE_GUIDE.md` — voice catalogue & use cases
- `DEEP_ARCHITECTURE.md` / `professional_architecture.md` — design notes
- `YOUTUBE_UPLOAD_PLAN.md` / `AUTO_SCRIPT_PLAN.md` — feature plans
