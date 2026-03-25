# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 專案說明

這是 Ternence 開發的 Whisper 語音工具（v1.1.0），提供圖形化介面，支援 Mac 與 Windows。

## 目錄結構

```
Whisper/
├── Whisper_開發版_整理版/       ← 開發主目錄（平常在這裡工作）
├── Whisper_Mac_一鍵安裝版/      ← Mac 新手發佈包
├── Whisper_Windows_一鍵安裝版/  ← Windows 新手發佈包
└── archive_old_2026-02-26/     ← 舊版備份
```

## 開發環境建立與啟動

開發版位於 `Whisper_開發版_整理版/`，需 Python 3.12 + ffmpeg + tcl-tk（透過 Homebrew）。

```bash
# 第一次：建立 .venv 並安裝依賴
cd Whisper_開發版_整理版
./setup_dev_env.sh

# 啟動 GUI
./run_whisper_gui.sh

# 命令列轉錄（自動語言）
./run_whisper_auto.sh <音檔路徑>

# 命令列轉錄（指定中文）
./run_whisper_zh.sh <音檔路徑>
```

依賴套件（`requirements-dev.txt`）：
- `openai-whisper==20250625`
- `opencc-python-reimplemented>=0.1.7`（簡繁轉換）

## 核心架構

所有版本（開發版、Mac 版、Windows 版）共用相同的單檔 GUI 程式架構：

- **`whisper_gui.py`**（開發版）/ `whisper_gui_mac.py` / `whisper_gui_win.py`：單一檔案 tkinter 應用
- **`WhisperApp` class**：包含全部 UI 建構、轉錄與 TTS 邏輯
  - 介面以 `ttk.Notebook` 分成「語音轉字幕」與「文字轉語音」兩個分頁
  - 轉錄與 TTS 都在背景 thread 執行，UI 不卡頓
  - 停止轉錄使用 `ctypes.pythonapi.PyThreadState_SetAsyncExc`（強制中止 thread）
  - 已載入的模型快取在 `self.model_cache` dict，避免重複載入
- **輸出格式**：`.txt`、`.srt`、`.vtt`，存放於與輸入檔同目錄，檔名格式為 `{原檔名}_{偵測語言}.{副檔名}`
- **中文繁化**：偵測語言為中文時，使用 OpenCC config `s2twp` 轉為繁體中文（`_to_traditional`）
- **文字轉語音**：使用 `edge-tts` 產生 `.mp3`，長文會先分段再透過 `ffmpeg` 合併

## 版本間差異

| 版本 | 說明 |
|------|------|
| 開發版 | 使用 `setup_dev_env.sh` 建立 `.venv`，ffmpeg 由 Homebrew 安裝 |
| Mac 版 | `setup_and_run_mac.sh` 包含完整 Homebrew + Python + ffmpeg 安裝流程，含 `download_model.py` |
| Windows 版 | 內建 `ffmpeg/` 目錄，使用 PowerShell (`setup_and_run.ps1`) + `.bat` 啟動 |

## 打包給新手前

先執行清理腳本，移除 `.venv`、模型快取、macOS 暫存檔：

```bash
# Mac 版
./Whisper_Mac_一鍵安裝版/99-打包前清理.command

# Windows 版
Whisper_Windows_一鍵安裝版\99-打包前清理.bat
```
