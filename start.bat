@echo off
chcp 65001 >nul
cd /d "%~dp0"
title Accounting Tracker

where py >nul 2>nul && (set "PY=py -3") || (set "PY=python")

if not exist ".venv\Scripts\python.exe" (
    echo [1/3] Creating Python environment...
    %PY% -m venv .venv
    if errorlevel 1 goto :nopython
)

echo [2/3] Installing libraries (first run takes a few minutes)...
".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -q -r requirements.txt
if errorlevel 1 goto :pipfail

if not exist "%USERPROFILE%\.streamlit\credentials.toml" (
    mkdir "%USERPROFILE%\.streamlit" 2>nul
    (echo [general]& echo email = "") > "%USERPROFILE%\.streamlit\credentials.toml"
)

echo [3/3] Starting the app. Your browser will open at http://localhost:8501
echo Close this window to stop the app.
".venv\Scripts\python.exe" -m streamlit run app.py --server.headless false
pause
exit /b

:nopython
echo.
echo Python was not found. Install it from https://www.python.org/downloads/ and tick "Add python.exe to PATH".
pause
exit /b

:pipfail
echo.
echo Library install failed. Check your internet connection and run this file again.
pause
