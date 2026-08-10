@echo off
setlocal
title ADX Drum MIDI Player

rem FluidSynth and SoundFont paths are resolved by play_server.py.
rem Double-click this file to start the playback service and open the browser player.
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
    echo Check Python, FluidSynth, and SoundFont configuration in play_server.py.
    pause
)
endlocal
