@echo off
chcp 65001 >nul
cd /d "%~dp0"
powershell -NoProfile -Command "Unregister-ScheduledTask -TaskName 'Trading Dashboard Wochenbericht' -Confirm:$false; Write-Host 'Aufgabe entfernt.'"
echo.
pause
