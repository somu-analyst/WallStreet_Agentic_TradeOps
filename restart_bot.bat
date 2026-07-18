@echo off
title NYSE Telegram Bot - RESTART
cd /d "%~dp0"

echo.
echo   NYSE Telegram Bot  --  RESTART (reload latest code)
echo   ----------------------------------------------------
echo   Stops the running bot + dashboard, then starts a fresh bot.
echo   The bot re-launches a clean dashboard on startup.
echo.

echo   [1/3] Stopping running bot + dashboard...
powershell -NoProfile -Command "Get-CimInstance Win32_Process | Where-Object { $_.Name -like 'python*' -and $_.CommandLine -match 'telegram_bot_optimized|dashboard\.py' } | ForEach-Object { Write-Host ('        killing PID ' + $_.ProcessId); Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }"

echo   [2/3] Waiting for single-instance lock to release...
timeout /t 3 /nobreak >nul

echo   [3/3] Starting the bot (leave THIS window open; Ctrl+C stops it)...
echo.
python telegram_bot_optimized.py

echo.
echo   The bot has stopped.
pause
