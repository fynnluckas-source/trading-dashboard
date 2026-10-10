@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo COT-Daten auffrischen ...
.venv\Scripts\python.exe cot.py >nul
echo Seite bauen ...
.venv\Scripts\python.exe build_seite.py --auf
echo.
pause
