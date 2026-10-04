@echo off
title Roblox Verification Discord Bot
cd /d "%~dp0"

echo ========================================================
echo         Roblox Verification Discord Bot Launcher
echo ========================================================
echo.

where python >nul 2>nul
if %errorlevel% neq 0 (
    echo [ERROR] Python is not found in your PATH!
    echo Please install Python 3.10+ from python.org and check "Add Python to PATH".
    pause
    exit /b 1
)

echo Checking dependencies...
python -m pip install -r requirements.txt --quiet

echo.
echo Starting bot...
python bot.py

echo.
echo Bot stopped.
pause
