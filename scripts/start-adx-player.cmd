@echo off
setlocal
title ADX Drum MIDI Player

cd /d "%~dp0"

where py >nul 2>nul
if %errorlevel%==0 (
    py -3 "%~dp0play_server.py"
) else (
    python "%~dp0play_server.py"
)

if errorlevel 1 (
    echo.
    echo ADX MIDI player failed to start.
    echo Confirm that play_server.py, slot_map_definitions.json, and accent_levels.json are in this folder.
    pause
)
endlocal
