@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo %date% %time% >> wochenbericht_log.txt
.venv\Scripts\python.exe wochenbericht.py >> wochenbericht_log.txt 2>&1
