@echo off
echo Menyiapkan Bot Sinyal Trading...
echo ====================================

:: Cek apakah venv ada
if not exist "venv\Scripts\activate.bat" (
    echo [ERROR] Virtual Environment belum dibuat atau hilang.
    echo Silakan jalankan: python -m venv venv
    pause
    exit /b
)

:: Mengaktifkan VENV dan langsung menjalankan script python
call ".\venv\Scripts\activate.bat"
python listener.py

echo.
echo ====================================
echo Bot telah berhenti.
pause
