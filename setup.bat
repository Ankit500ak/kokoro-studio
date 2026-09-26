@echo off
echo ========================================
echo    Kokoro Studio - Setup
echo ========================================
echo.

echo [1/3] Installing backend dependencies...
cd backend
if not exist venv (
    python -m venv venv
)
call venv\Scripts\activate.bat
pip install -r requirements.txt
echo.

echo [2/3] Installing frontend dependencies...
cd ..\frontend
npm install
echo.

echo [3/3] Setup complete!
echo.
echo To start the application:
echo   1. Run start-backend.bat
echo   2. Run start-frontend.bat
echo.
echo Then open http://localhost:5174
echo.
pause
