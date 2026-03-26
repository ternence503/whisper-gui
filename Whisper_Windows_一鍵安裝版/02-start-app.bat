@echo off
setlocal

set SCRIPT_DIR=%~dp0
powershell -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT_DIR%_internal\setup_and_run.ps1" -OnlyLaunch
set EXIT_CODE=%ERRORLEVEL%

if NOT "%EXIT_CODE%"=="0" (
  echo.
  echo [ERROR] Launch failed. Please run 01-install-and-run.bat first if not yet installed.
  echo         Screenshot this window and send for help if the problem persists.
  pause
  exit /b %EXIT_CODE%
)

echo.
echo Done. Press any key to close.
pause
exit /b 0
