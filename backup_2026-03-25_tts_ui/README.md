# Whisper 開發版（整理版）

這是從原本雜亂的開發目錄整理出來的乾淨版本，現在同時支援：

- 語音轉字幕
- 文字轉語音（TTS，輸出 MP3）

## 署名資訊

- 作者：Ternence
- 版本：v1.1.0


## 你平常自己用這包的方式

1. 第一次雙擊 `01-建立開發環境.command`
2. 需要離線使用時，雙擊 `03-下載模型.command` 預先下載模型（需聯網一次）
3. 完成後雙擊 `02-啟動GUI.command`
4. 之後只要雙擊 `02-啟動GUI.command` 就能啟動（含離線）

## 指令列腳本

- `run_whisper_gui.sh`：啟動 GUI
- `run_whisper_auto.sh <檔案> [模型]`：自動語言轉錄（模型預設 small）
- `run_whisper_zh.sh <檔案> [模型]`：以中文語言模式轉錄（模型預設 small）

## 目錄重點

- `whisper_gui.py`：主 GUI 程式
- `setup_dev_env.sh`：建立 `.venv` 與安裝依賴
- `download_model.py`：手動下載模型到 `models/`（供離線使用）
- `requirements-dev.txt`：Python 套件清單
- `.venv/`：本地虛擬環境（建立後出現）
- `models/`：預下載的 Whisper 模型（存在時優先使用，可離線執行）

## 支援檔案

可直接選取音檔或影片（例如 mp3/wav/mp4/mov/mkv）進行轉錄。
中文內容會自動轉為繁體；外語內容維持原文輸出。

文字轉語音可在 GUI 的「文字轉語音」分頁中使用：

- 貼上文字
- 選擇中文男聲或女聲
- 設定語速與音高
- 輸出為 `mp3`

長文會自動分段合成後再合併，避免一次送出過長內容導致失敗。

## 系統需求

- macOS 12 以上
- Python 3.12（由 `setup_dev_env.sh` 透過 Homebrew 安裝）
- ffmpeg（由 `setup_dev_env.sh` 透過 Homebrew 安裝）

## 備註

- 原本舊資料夾保留不動，這份是新的整理版。
- 若要給新手，請優先使用：
  - `Whisper_Mac_一鍵安裝版`（macOS 12+）
  - `Whisper_Windows_一鍵安裝版`（**Windows 10 以上，不支援 Windows 7 / 8 / 8.1**）
