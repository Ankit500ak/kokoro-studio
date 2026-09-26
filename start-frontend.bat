@echo off
title Kokoro Studio Frontend
echo ============================================
echo   Kokoro Studio Frontend
echo   http://localhost:5174
echo ============================================
echo.

:: Change to frontend directory
cd /d "%~dp0frontend"

:: Check if node_modules exists, if not install
if not exist node_modules (
    echo Installing npm dependencies...
    call npm install
)

:: Check if vite is available, if not global install
if not exist node_modules\.bin\vite.exe (
    echo Installing Vite globally...
    call npm install -g vite
)

:: Start the frontend development server
echo Starting frontend server...
call npm run dev

:: Keep window open
pause