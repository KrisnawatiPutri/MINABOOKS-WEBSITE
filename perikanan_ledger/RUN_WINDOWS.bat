@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Virtual environment belum dibuat.
  echo Ikuti README.md bagian instalasi terlebih dahulu.
  pause
  exit /b 1
)
start "" http://127.0.0.1:8000/
".venv\Scripts\python.exe" manage.py runserver
pause
