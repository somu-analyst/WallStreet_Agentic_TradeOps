@echo off
REM ONE entry point (ID 283): starts the Telegram bot if it is not already running,
REM starts the Streamlit server if the port is dead, then opens the installed app window.
REM Replaces having to pick between run_bot.bat and a separate dashboard launcher.
cd /d "%~dp0"
start "" pythonw dashboard_app.py --with-bot
