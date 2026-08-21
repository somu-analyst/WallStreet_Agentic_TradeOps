@echo off
REM Double-click (or pin) to open the dashboard as an app window.
REM Starts the Streamlit server first if it is not already running.
cd /d "%~dp0"
start "" pythonw dashboard_app.py
