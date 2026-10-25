@echo off
title Remove Microsoft Rewards Tracker From Auto-Start
powershell -Command "$p=[Environment]::GetFolderPath('Startup') + '\MSRewardsTracker.lnk'; if (Test-Path $p) { Remove-Item $p; Write-Host 'Removed from Startup!' } else { Write-Host 'Shortcut was not in Startup.' }"
echo.
pause
