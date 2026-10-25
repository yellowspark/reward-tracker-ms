@echo off
title Microsoft Rewards Gift Card Tracker
cd /d "%~dp0"
echo =========================================================
echo   Starting Microsoft Rewards Gift Card Restock Tracker
echo =========================================================
echo Dashboard URL: http://localhost:5001
echo.
timeout /t 2 /nobreak >nul
start http://localhost:5001
python app.py
pause
