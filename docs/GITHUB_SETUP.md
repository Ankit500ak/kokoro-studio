# GitHub & Data Setup Guide

This repo contains **code only (~1.2 MB)**. Everything large is gitignored and lives on
your machine (or in a GitHub Release). This document explains:

1. what is excluded and why
2. how to get the data back after cloning
3. how to publish data as a GitHub Release
4. the everyday git workflow

---

## 1. What is in git vs. what is not

| Path | Size | In git? | Where it comes from |
|---|---|---|---|
| `backend/app/`, `frontend/src/`, scripts, docs | ~1.2 MB | ✅ | this repo |
| `backend/.env` | KB | ❌ | copy from `backend/.env.example` and fill in |
| `backend/venv/` | 1.5 GB | ❌ | `setup.bat` |
| `frontend/node_modules/`, `frontend/dist/` | ~400 MB | ❌ | `setup.bat` |
| TTS model weights (Kokoro-82M + espeak) | ~0.5 GB | ❌ | auto-download on first synthesis |
| `backend/app/storage/media/` | 7 GB | ❌ | your video library — Release asset or manual copy |
| `backend/app/storage/renders/` | 35 GB | ❌ | generated output — **regenerate, never back up** |
| `backend/app/storage/audio/` | 1.7 GB | ❌ | generated TTS WAVs — regeneratable |
| `backend/app/storage/kokoro.db` | ~8 MB | ❌ | auto-created on first start (or restore from Release) |
| `videotemplate/` | 866 MB | ❌ | template clips — Release asset or manual copy |
| `.opencode/`, `*.log`, `nul`, scratch `fix_*.py` | — | ❌ | local junk, intentionally ignored |

`.gitignore` enforces all of this. If you add a new large data folder, add it there too.

---

## 2. First-time setup after cloning

```bat
git clone https://github.com/heywinterbell/kokoro-studio.git
cd kokoro-studio

setup.bat                       :: creates backend\venv, pip install, npm install

copy backend\.env.example backend\.env
notepad backend\.env            :: add NVIDIA / Telegram / YouTube keys

start.bat                       :: backend :8000 + frontend :5174 + telegram bot
```

Verify: http://localhost:5174 loads and http://localhost:8000/docs returns JSON.

The app creates any missing folders (`backend/app/storage/*`, `backend/logs/`) on startup,
so a fresh clone boots fine — it just has no media library and an empty database until
you restore data.

---

## 3. Getting the large data

### Option A — from an existing machine (simplest, no upload)

Run from the **repo root on the new machine**, with the source path pointing at the old
checkout:

```powershell
$src = "C:\Users\Admin\Desktop\reader\VOICE APP\kokoro-studio"

# video library (7 GB)
robocopy "$src\backend\app\storage\media"  "backend\app\storage\media"  /E /MT:16 /R:2 /W:2

# template clips (866 MB)
robocopy "$src\videotemplate" "videotemplate" /E /MT:16 /R:2 /W:2

# database (stop the backend first!)
robocopy "$src\backend\app\storage" "backend\app\storage" "kokoro.db*" /R:2 /W:2

# secrets
robocopy "$src\backend" "backend" .env
```

Skip `renders\` and `audio\` on purpose — they are output, not source data.

### Option B — from a GitHub Release (fresh machine / another person)

```powershell
# list available data releases
gh release list --repo heywinterbell/kokoro-studio

# download every asset of the data release (~8 GB)
gh release download data-v1 --repo heywinterbell/kokoro-studio --dir _data

# unpack into the repo root (zips keep the real folder structure)
Get-ChildItem _data\*.zip | ForEach-Object {
    Write-Host "Extracting $($_.Name)..."
    Expand-Archive $_.FullName -DestinationPath . -Force
}
Remove-Item _data -Recurse -Force
```

Or, without the GitHub CLI: open
https://github.com/heywinterbell/kokoro-studio/releases → download the zips → extract each
one **into the repo root** (`kokoro-studio/`), so `media/` lands in
`backend/app\storage\media\` etc.

After restoring, restart the backend so it re-scans the media library.

### Option C — models (nothing to do)

Kokoro weights are pulled from Hugging Face by the `kokoro` pip package on the **first
synthesis** and cached in `%USERPROFILE%\.cache\huggingface\hub`. Expect a one-off
download (~0.5 GB) and a slow first generation. To pre-warm:

```powershell
backend\venv\Scripts\python -c "from kokoro import KPipeline; KPipeline(lang_code='a')"
```

> FFmpeg must also be installed separately (see README) — it is not bundled.

---

## 4. Publishing data as a GitHub Release

**Rules of the road**

- Each release asset must be **< 2 GiB** (GitHub hard limit).
- There is **no limit** on total release size or download bandwidth.
- Up to 1000 assets per release — one release holds all of this data.
- Stop the backend before packing the database so `kokoro.db` is not mid-write.

```powershell
# build the zips (auto-splits big folders into <2 GB parts)
powershell -ExecutionPolicy Bypass -File scripts\pack-data.ps1 -Tag data-v1

# ...then publish them
powershell -ExecutionPolicy Bypass -File scripts\pack-data.ps1 -Tag data-v1 -Upload
```

Useful variants:

```powershell
# media library only
scripts\pack-data.ps1 -Tag data-v1 -SkipTemplates -SkipDb

# smaller parts (1 GB each) - more files, safer on flaky connections
scripts\pack-data.ps1 -Tag data-v1 -MaxPartMB 1000

# publish under a new tag
scripts\pack-data.ps1 -Tag data-v2 -Upload
```

Zips are written to `release-assets/` which is **gitignored** — they never enter the repo.
Re-running with the same `-Tag` overwrites existing assets (`gh release upload --clobber`).

To add a note or edit later:

```powershell
gh release edit data-v1 --repo heywinterbell/kokoro-studio --notes "Media library snapshot 2026-09-26"
```

---

## 5. Everyday git workflow

```powershell
git status                      # ALWAYS look before you commit
git diff                        # what changed in tracked files

git add -A                      # stage everything (ignored files stay out)
git commit -m "feat: add caption burn-in timing control"
git push
```

Feature branch + PR (preferred for anything non-trivial):

```powershell
git checkout -b feat/my-change
# ... edit, commit ...
git push -u origin feat/my-change
gh pr create --fill
gh pr merge --squash --delete-branch
```

Keep the main branch clean:

```powershell
git checkout main
git pull
```

### Before every commit, check these

1. `git status` shows **no** `.env`, `storage/`, `*.mp4`, `*.wav`, `venv/`, `node_modules/`
2. no file over ~1 MB: `git status --porcelain | ForEach-Object { Get-Item ($_.Substring(3)) } | Sort Length -Desc | Select -First 10`
3. no secrets pasted into code (keys belong in `backend/.env` only)

### If you accidentally commit something big

```powershell
# unstage / remove it from the last commit, keeping the file on disk
git rm --cached -r "path\to\large-file"
git commit --amend

# for older commits, rewrite history before pushing:
git filter-repo --path "backend/app/storage" --invert-paths
# (install first: pip install git-filter-repo)
```

Git will reject individual files over **100 MB** and warns over 50 MB — that is your last
line of defence, don't rely on it.

---

## 6. Never commit list

| Never | Why |
|---|---|
| `backend/.env` | API keys, bot token, YouTube client secret |
| `backend/app/storage/**` | 44 GB user data & output |
| `videotemplate/**` | 866 MB licensed/stock footage |
| `venv/`, `node_modules/`, `dist/` | reproducible from `setup.bat` |
| model weights (`*.onnx`, `*.safetensors`, `*.pt`, …) | auto re-downloaded |
| YouTube OAuth tokens (from the DB) | stored encrypted in `kokoro.db`, which is ignored |

`.env.example` is the template that **is** committed — keep it in sync whenever you add a
new setting.

---

## 7. Troubleshooting

| Symptom | Fix |
|---|---|
| Frontend loads, API calls 404 | backend not running → `start-backend.bat` |
| "port 8000 already in use" | `start-backend.bat` kills only that port's PID; or find it: `netstat -ano \| findstr :8000` |
| Empty media library | restore data (§3) then use **Media → Scan directory** in the UI, or `backend\venv\Scripts\python backend\import_videos.py` |
| First TTS call hangs for minutes | normal — model download. Pre-warm with the command in §3 Option C |
| `cryptography` / `dotenv` import errors | `backend\venv\Scripts\pip install -r backend\requirements.txt` |
| Git is tracking a file it shouldn't | `git rm --cached <file>`, add it to `.gitignore`, commit |
| Release upload fails at ~2 GB | a part is too big — repack with `-MaxPartMB 1900` or lower |
