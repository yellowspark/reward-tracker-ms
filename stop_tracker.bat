@echo off
title Stop Microsoft Rewards Tracker
echo Stopping Microsoft Rewards Tracker on port 5001...

powershell -Command "Get-NetTCPConnection -LocalPort 5001 -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess | ForEach-Object { Stop-Process -Id $_ -Force -ErrorAction SilentlyContinue; Write-Host 'Stopped Tracker PID: ' $_ }"

echo.
echo Microsoft Rewards Tracker has been stopped.
ping 127.0.0.1 -n 2 >nul
