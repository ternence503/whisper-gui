@echo off
REM Pre-packaging cleanup: remove local models, ffmpeg cache and pycache
setlocal
set DIR=%~dp0
set INTERNAL=%DIR%_internal

echo Cleaning up...

REM Whisper models (stored in %LOCALAPPDATA%\WhisperGui after install)
if exist "%INTERNAL%\models\" (
    echo   Removing models...
    rmdir /s /q "%INTERNAL%\models"
)

REM FFmpeg binaries (stored in %LOCALAPPDATA%\WhisperGui after install)
if exist "%INTERNAL%\ffmpeg\" (
    echo   Removing ffmpeg...
    rmdir /s /q "%INTERNAL%\ffmpeg"
)

REM Python cache
if exist "%DIR%__pycache__\" (
    echo   Removing __pycache__...
    rmdir /s /q "%DIR%__pycache__"
)
if exist "%INTERNAL%\__pycache__\" (
    rmdir /s /q "%INTERNAL%\__pycache__"
)

echo.
echo Cleanup complete. Ready to package.
pause
