@echo off
title Kokoro Studio - Launch All Components
echo Starting Kokoro Studio components...
echo.

:: Start Backend in new window
start "Kokoro Backend" call start-backend.bat

:: Start Frontend in new window
start "Kokoro Frontend" call start-frontend.bat

:: Start Telegram Bot in new window
start "Kokoro Telegram" call telegram.bat

echo.
echo All components launched in separate windows.
echo Each window will open the respective component and pause.
echo Close this terminal to exit.
timeout /t 5 /nobreak >nul
exit