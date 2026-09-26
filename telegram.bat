@echo off
title Kokoro Telegram Auto-Pilot
echo Starting Kokoro Telegram Auto-Pilot Bot...

:: Secrets (bot token) now live in backend\.env -- do not hardcode them here.
cd /d "%~dp0backend"
call venv\Scripts\activate.bat

:: Ensure cryptography is available (required for YouTube token encryption)
echo Checking required packages...
python -c "from cryptography.fernet import Fernet" >nul 2>&1
if errorlevel 1 (
    echo Installing cryptography...
    pip install "cryptography>=42.0.0" >nul 2>&1
)
python -c "from dotenv import load_dotenv" >nul 2>&1
if errorlevel 1 (
    echo Installing python-dotenv...
    pip install python-dotenv >nul 2>&1
)
python -c "from cryptography.fernet import Fernet" >nul 2>&1
if errorlevel 1 (
    echo ERROR: cryptography module not available
    pause
    exit /b 1
)

if not defined TELEGRAM_BOT_TOKEN (
    findstr /B /C:"TELEGRAM_BOT_TOKEN=" .env >nul 2>&1
    if errorlevel 1 (
        echo ERROR: TELEGRAM_BOT_TOKEN is not set. Add it to backend\.env
        pause
        exit /b 1
    )
)

:: Run the bot
echo Starting Telegram bot...
python telegram_bot.py

echo Bot terminated.
pause
