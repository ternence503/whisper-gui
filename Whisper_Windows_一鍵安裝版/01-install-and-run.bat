@echo off
setlocal

set SCRIPT_DIR=%~dp0
powershell -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT_DIR%setup_and_run.ps1" %*
set EXIT_CODE=%ERRORLEVEL%

if NOT "%EXIT_CODE%"=="0" (
  echo.
  echo [ERROR] Installation or launch failed. Please screenshot this window and send for help.
  pause
  exit /b %EXIT_CODE%
)

echo.
echo Done. Press any key to close.
pause
exit /b 0
