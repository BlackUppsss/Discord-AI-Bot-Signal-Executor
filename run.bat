@echo off
echo Menyiapkan Bot Sinyal Trading...
echo ====================================

if not exist "venv\Scripts\activate.bat" (
    echo [ERROR] Virtual Environment belum dibuat atau hilang.
    echo Silakan jalankan: python -m venv venv
    pause
    exit /b
)

call ".\venv\Scripts\activate.bat"
python src\listener.py

echo.
echo ====================================
echo Bot telah berhenti.
pause
