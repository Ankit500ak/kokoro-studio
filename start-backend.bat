@echo off
title Kokoro Studio Backend
echo ============================================
echo   Kokoro Studio Backend
echo   http://localhost:8000
echo ============================================
echo.

:: Kill only whatever is listening on port 8000.
:: Never run a blanket `taskkill /IM python.exe` - that kills every Python
:: process on the machine (TTS workers, other projects, this script's own venv).
echo Checking port 8000...
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":8000" ^| findstr "LISTENING" 2^>nul') do (
    echo Killing existing process on port 8000 (PID: %%a)
    taskkill /F /PID %%a >nul 2>&1
)
timeout /t 2 /nobreak >nul

:: Start backend using venv
echo Starting backend...
cd /d "%~dp0backend"
call venv\Scripts\activate.bat

:: Verify required packages are available (no pip install on every start)
echo Verifying required packages...
python -c "from cryptography.fernet import Fernet; import fastapi, uvicorn, dotenv, multipart" >nul 2>&1
if errorlevel 1 (
    echo Installing missing requirements...
    pip install --upgrade pip >nul 2>&1
    pip install "cryptography>=42.0.0" "fastapi>=0.109.0" "uvicorn[standard]" python-multipart "pydantic>=2.5.0" python-dotenv 2>nul
)

python -c "from cryptography.fernet import Fernet" >nul 2>&1
if errorlevel 1 (
    echo ERROR: cryptography module still not available
    pause
    exit /b 1
)

echo Required packages verified.

:: Start uvicorn
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --log-level info
pause
