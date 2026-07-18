@echo off
title NYSE Telegram Bot
cd /d "%~dp0"

echo.
echo   NYSE Telegram Bot  (telegram_bot_optimized.py)
echo   ---------------------------------------------
echo   Starting the bot. It polls Telegram until you close this window.
echo   Leave THIS window open. Ctrl+C stops the bot.
echo.

python telegram_bot_optimized.py

echo.
echo   The bot has stopped.
pause
