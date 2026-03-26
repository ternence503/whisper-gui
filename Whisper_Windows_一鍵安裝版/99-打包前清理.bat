@echo off
setlocal
cd /d "%~dp0"

echo [Developer tool] Pre-release cleanup
echo This removes .venv, models, ffmpeg binaries and caches.
echo.
set /p CONFIRM=Confirm cleanup (y/N)?
if /I not "%CONFIRM%"=="y" (
  echo Cancelled.
  goto :END
)

echo [1/4] Removing .venv...
if exist "_internal\.venv" rmdir /s /q "_internal\.venv"

echo [2/4] Removing models...
if exist "_internal\models" (
  for /d %%D in ("_internal\models\*") do rmdir /s /q "%%~fD"
  for %%F in ("_internal\models\*") do (
    if /I not "%%~nxF"==".gitkeep" del /f /q "%%~fF"
  )
)

echo [3/4] Removing ffmpeg binaries...
if exist "_internal\ffmpeg" (
  for /d %%D in ("_internal\ffmpeg\*") do rmdir /s /q "%%~fD"
  for %%F in ("_internal\ffmpeg\*") do (
    if /I not "%%~nxF"==".gitkeep" del /f /q "%%~fF"
  )
)

echo [4/4] Removing cache files...
for /d /r %%D in (__pycache__) do (
  if exist "%%~fD" rmdir /s /q "%%~fD"
)
del /s /f /q "*.pyc" >nul 2>nul

echo Done. Ready to zip and distribute.

:END
echo.
pause
exit /b 0
