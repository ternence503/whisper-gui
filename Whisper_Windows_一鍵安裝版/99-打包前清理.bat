@echo off
setlocal
cd /d "%~dp0"

echo 將清理以下內容：
echo - .venv (Python 虛擬環境)
echo - models 內模型檔（保留 .gitkeep）
echo - ffmpeg 內執行檔（保留 .gitkeep）
echo - __pycache__ 與 *.pyc
echo.
set /p CONFIRM=確認清理 (y/N)？
if /I not "%CONFIRM%"=="y" (
  echo 已取消。
  goto :END
)

echo [1/4] 清理 .venv...
if exist ".venv" rmdir /s /q ".venv"

echo [2/4] 清理 models...
if exist "models" (
  for /d %%D in ("models\*") do rmdir /s /q "%%~fD"
  for %%F in ("models\*") do (
    if /I not "%%~nxF"==".gitkeep" del /f /q "%%~fF"
  )
)

echo [3/4] 清理 ffmpeg...
if exist "ffmpeg" (
  for /d %%D in ("ffmpeg\*") do rmdir /s /q "%%~fD"
  for %%F in ("ffmpeg\*") do (
    if /I not "%%~nxF"==".gitkeep" del /f /q "%%~fF"
  )
)

echo [4/4] 清理快取...
for /d /r %%D in (__pycache__) do (
  if exist "%%~fD" rmdir /s /q "%%~fD"
)
del /s /f /q "*.pyc" >nul 2>nul

echo 清理完成，現在可直接壓縮整個資料夾給新手。

:END
echo.
pause
exit /b 0
