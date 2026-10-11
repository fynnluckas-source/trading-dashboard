@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo Richtet eine geplante Aufgabe in Windows ein:
echo Jeden Samstag um 09:00 Uhr wird der Trading-Wochenbericht in dein Vault geschrieben.
echo War der PC dann aus, wird der Bericht nachgeholt, sobald er wieder an ist.
echo.
powershell -NoProfile -Command "$a = New-ScheduledTaskAction -Execute '\"%~dp0Wochenbericht Hintergrund.bat\"' -WorkingDirectory '%~dp0'; $t = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Saturday -At 09:00; $s = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries; Register-ScheduledTask -TaskName 'Trading Dashboard Wochenbericht' -Action $a -Trigger $t -Settings $s -Force | Out-Null; Write-Host 'Fertig: Aufgabe Trading Dashboard Wochenbericht ist eingerichtet.'"
echo.
echo Wieder entfernen kannst du sie mit "Wochenbericht Automatik entfernen.bat".
echo.
pause
