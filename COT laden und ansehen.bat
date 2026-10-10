@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo COT-Daten werden von der CFTC geladen ...
.venv\Scripts\python.exe cot.py
echo.
echo ===== Neueste Zahlen =====
echo.
.venv\Scripts\python.exe cot_ansehen.py
pause
