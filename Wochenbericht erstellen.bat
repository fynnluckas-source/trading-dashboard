@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo Wochenbericht erstellen ...
.venv\Scripts\python.exe wochenbericht.py
echo.
pause
