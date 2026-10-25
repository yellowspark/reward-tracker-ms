@echo off
title Auto-Start Microsoft Rewards Tracker On Boot
cd /d "%~dp0"

echo Creating Windows Startup shortcut...
powershell -Command "$s=(New-Object -COM WScript.Shell).CreateShortcut([Environment]::GetFolderPath('Startup') + '\MSRewardsTracker.lnk'); $s.TargetPath='%~dp0start_background.vbs'; $s.WorkingDirectory='%~dp0'; $s.Save(); Write-Host 'Successfully added to Windows Startup!'"

echo.
echo Microsoft Rewards Tracker will now start silently in the background whenever your PC starts.
pause
