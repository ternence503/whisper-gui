# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 專案說明

這是 Ternence 開發的 Whisper 語音工具（v1.1.0），提供圖形化介面，支援 Mac 與 Windows。

## 每次開啟先閱讀

開新對話或由其他 AI / 人員接手這個專案時，請先依序閱讀：

1. Ternence 提供的全域背景文件「Ternence 的開發背景資訊」
2. 本專案的 `CLAUDE.md`
3. `Whisper_開發版_整理版/README.md`

目的：

- 先確認工作硬碟、Git 規則、其他專案隔離原則
- 再理解 Whisper 專案自己的架構與目前功能
- 最後確認開發版 GUI 的使用方式與環境建立流程

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
- `edge-tts>=7.2.8`（文字轉語音）

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
  - GUI 目前提供語速選項：`-10%`、`0%`、`+5%`、`+10%`、`+20%`
  - GUI 目前提供音高選項：`-2Hz`、`0Hz`、`+2Hz`、`+4Hz`
  - 預設值為語速 `+5%`、音高 `+2Hz`
  - 已有保守型「朗讀優化」：只調整斷句、時間、電話、網址的朗讀形式，不改活動資訊本身

## 目前待辦

- **TTS 時長壓縮模式尚未完成**：如果原稿約 5 分鐘，要壓到約 2 分鐘，不能只靠提高語速，否則中文咬字與停頓會明顯不自然。
- 建議後續實作「精簡旁白模式」：先把原文濃縮成較短旁白稿，再搭配中度語速提升，而不是單純把 `edge-tts` 語速拉高。
- 若後續接手這一段，優先方向應為：
  - 保留「原文直出」
  - 新增「2 分鐘精簡版」或「短影音版」
  - 在 GUI 顯示預覽文字，讓使用者確認精簡後內容再輸出

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
