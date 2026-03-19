# Windows 新手包（Whisper_Windows_一鍵安裝版）

這個資料夾是給 Windows 入門者使用，目標是「一鍵安裝、一鍵啟動」。

## 署名資訊

- 作者：Ternence
- 版本：v1.0.0


## 使用者怎麼操作

1. 把整個 `Whisper_Windows_一鍵安裝版` 資料夾複製到 Windows（例如桌面 `WhisperWin`）。
2. 雙擊 `01-install-and-run.bat`。
3. 第一次會自動完成：
   - Python 環境建立
   - 套件安裝
   - FFmpeg 下載
   - Whisper 模型下載（預設 `small`）
4. 安裝完會自動開啟 GUI。
5. 之後直接雙擊 `02-start-app.bat` 即可啟動。
6. 可直接選擇音檔或影片（例如 mp3/wav/mp4/mov/mkv），程式會自動轉成文字。
7. 中文內容會自動轉為繁體；外語內容維持原文輸出。

## 發佈前清理（建議）

如果你要把這包傳給別人，先雙擊：

- `99-打包前清理.bat`

用途：
- 清掉 `.venv`、模型、ffmpeg 與快取暫存
- 降低檔案體積
- 避免把你本機狀態一起打包出去

## 第一次安裝需求

- 需要網路（只要第一次）。
- 建議 Windows 10/11 64 位元。

## 要打包給別人時注意

- 這個 `Whisper_Windows_一鍵安裝版` 資料夾內的檔案請保持完整，不要拆開。
- 不要改名 `setup_and_run.ps1`、`whisper_gui_win.py`。
- 若第一次想改模型，可在命令列執行：
  - `01-install-and-run.bat medium`
  - `01-install-and-run.bat turbo`

## 轉錄輸出

輸出會存在原檔案同一個資料夾：

- `檔名_語言代碼.txt`
- `檔名_語言代碼.srt`
- `檔名_語言代碼.vtt`
