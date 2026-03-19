@echo off
setlocal

set SCRIPT_DIR=%~dp0
powershell -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT_DIR%setup_and_run.ps1" -OnlyLaunch
set EXIT_CODE=%ERRORLEVEL%

if NOT "%EXIT_CODE%"=="0" (
  echo.
  echo 啟動失敗，請先執行 01-install-and-run.bat 安裝環境。
  pause
)

exit /b %EXIT_CODE%
