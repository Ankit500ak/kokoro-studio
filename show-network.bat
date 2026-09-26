@echo off
echo ========================================
echo    Kokoro Studio - Network Access
echo ========================================
echo.
echo Your network IP addresses:
echo.
for /f "tokens=2 delims=:" %%a in ('ipconfig ^| findstr /c:"IPv4"') do echo   http://%%a:5174
echo.
echo ========================================
echo.
echo Make sure both servers are running:
echo   1. start-backend.bat
echo   2. start-frontend.bat
echo.
echo Other devices on your network can now access:
echo   http://YOUR-IP:5174
echo.
pause
