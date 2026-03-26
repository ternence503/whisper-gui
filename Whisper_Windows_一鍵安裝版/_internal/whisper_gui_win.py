#!/usr/bin/env python3
"""簡易圖形介面的 Whisper 語音轉字幕工具 (CPU 版)。"""

from __future__ import annotations

import os
import threading
import ctypes
import sys
import io
import asyncio
import shutil
import subprocess
import tempfile
import re
from typing import Dict, Iterable, List, Optional

try:
    import tkinter as tk
    from tkinter import filedialog, messagebox, ttk
except ModuleNotFoundError as exc:
    raise SystemExit("目前的 Python 未啟用 tkinter，請安裝 tcl-tk 後再執行本工具。") from exc

import whisper
try:
    from opencc import OpenCC
except Exception:  # pragma: no cover
    OpenCC = None
try:
    import edge_tts
except Exception:  # pragma: no cover
    edge_tts = None

MODEL_OPTIONS: List[str] = [
    "base",
    "small",
    "medium",
    "large",
    "turbo",
]

MEDIA_FILE_PATTERNS = (
    "*.mp3 *.wav *.m4a *.aac *.flac *.ogg *.wma "
    "*.mp4 *.mov *.avi *.mkv *.webm *.m4v *.mpeg *.mpg"
)

APP_AUTHOR = "Ternence"
APP_VERSION = "v1.2.0"
APP_SIGNATURE = f"{APP_AUTHOR} {APP_VERSION}"
TTS_VOICE_OPTIONS: Dict[str, str] = {
    # 台灣腔
    "台灣女聲・活潑": "zh-TW-HsiaoYuNeural",    # Friendly, Positive（台灣國語腔）
    "台灣女聲・清亮": "zh-TW-HsiaoChenNeural",  # Friendly, Positive（台灣腔，咬字清晰）
    "台灣男聲・沉穩": "zh-TW-YunJheNeural",     # Friendly, Positive（台灣男聲）
    # 粵語腔
    "粵語女聲・活潑": "zh-HK-HiuGaaiNeural",   # Friendly, Positive（粵語女聲，語氣輕快）
    "粵語女聲・溫柔": "zh-HK-HiuMaanNeural",   # Friendly, Positive（粵語女聲，語氣柔和）
    "粵語男聲・友善": "zh-HK-WanLungNeural",   # Friendly, Positive（粵語男聲）
    # 普通話
    "普通話女聲・活潑": "zh-CN-XiaoyiNeural",  # Lively
    "普通話女聲・溫柔": "zh-CN-XiaoxiaoNeural", # Warm
    "普通話男聲・熱情": "zh-CN-YunjianNeural",  # Passion
    "普通話男聲・陽光": "zh-CN-YunxiNeural",   # Lively, Sunshine
    "普通話男聲・穩重": "zh-CN-YunyangNeural",  # Professional, Reliable
    "普通話男聲・可愛": "zh-CN-YunxiaNeural",  # Cute（偏童趣少年聲）
}
TTS_RATE_OPTIONS = ["-10%", "0%", "+5%", "+10%", "+20%", "+30%", "+40%", "+50%"]
TTS_PITCH_OPTIONS = ["-2Hz", "0Hz", "+2Hz", "+4Hz"]
TTS_MAX_CHARS = 900
TTS_SCRIPT_MODE_TARGETS: Dict[str, Optional[int]] = {
    "原文直出": None,
    "2 分鐘精簡版": 420,
    "短影音版": 220,
}
TTS_DIGIT_MAP = {
    "0": "零",
    "1": "一",
    "2": "二",
    "3": "三",
    "4": "四",
    "5": "五",
    "6": "六",
    "7": "七",
    "8": "八",
    "9": "九",
}

class _SilentStream(io.TextIOBase):
    def write(self, _data: str) -> int:
        return len(_data or "")

    def flush(self) -> None:  # pragma: no cover
        return None


def _ensure_stdio() -> None:
    if sys.stdout is None:
        sys.stdout = _SilentStream()
    if sys.stderr is None:
        sys.stderr = _SilentStream()


DEFAULT_OPTIONS = {
    "temperature": 0.0,
    "condition_on_previous_text": False,
    "no_speech_threshold": 0.4,
    "compression_ratio_threshold": 2.0,
}


def _format_timestamp(seconds: float, *, separator: str) -> str:
    if seconds is None:
        seconds = 0.0
    seconds = max(0.0, float(seconds))
    milliseconds = round(seconds * 1000)
    total_seconds, ms = divmod(milliseconds, 1000)
    minutes, sec = divmod(total_seconds, 60)
    hours, minutes = divmod(minutes, 60)
    if separator == ",":
        return f"{hours:02}:{minutes:02}:{sec:02},{ms:03}"
    return f"{hours:02}:{minutes:02}:{sec:02}.{ms:03}"


def _format_srt(segments: Iterable[Dict[str, float]]) -> str:
    lines: List[str] = []
    index = 1
    for seg in segments:
        text = seg.get("text", "").strip()
        if not text:
            continue
        start = _format_timestamp(seg.get("start", 0.0), separator=",")
        end = _format_timestamp(seg.get("end", 0.0), separator=",")
        lines.append(str(index))
        lines.append(f"{start} --> {end}")
        lines.append(text)
        lines.append("")
        index += 1
    return "\n".join(lines).strip() + "\n"


def _format_vtt(segments: Iterable[Dict[str, float]]) -> str:
    lines: List[str] = ["WEBVTT", ""]
    for seg in segments:
        text = seg.get("text", "").strip()
        if not text:
            continue
        start = _format_timestamp(seg.get("start", 0.0), separator=".")
        end = _format_timestamp(seg.get("end", 0.0), separator=".")
        lines.append(f"{start} --> {end}")
        lines.append(text)
        lines.append("")
    return "\n".join(lines).strip() + "\n"


def _configure_runtime_environment() -> None:
    base_path = os.path.dirname(sys.executable if getattr(sys, "frozen", False) else __file__)
    # Windows：搜尋根目錄與 ffmpeg/ 子目錄，同時確認 ffprobe.exe 存在
    ffmpeg_directories = [
        base_path,
        os.path.join(base_path, "ffmpeg"),
    ]
    for directory in ffmpeg_directories:
        ffmpeg_exe = os.path.join(directory, "ffmpeg.exe")
        ffprobe_exe = os.path.join(directory, "ffprobe.exe")
        if os.path.isfile(ffmpeg_exe) and os.path.isfile(ffprobe_exe):
            current_path = os.environ.get("PATH", "")
            path_items = current_path.split(os.pathsep) if current_path else []
            if directory not in path_items:
                os.environ["PATH"] = os.pathsep.join([directory, current_path]) if current_path else directory
            break

    model_dir = os.path.join(base_path, "models")
    if os.path.isdir(model_dir) and not os.environ.get("WHISPER_MODEL_DIR"):
        os.environ["WHISPER_MODEL_DIR"] = model_dir


_configure_runtime_environment()
_ensure_stdio()



class WhisperApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title(f"Whisper 語音工具：語音轉字幕 ＆ 文字轉語音 | {APP_SIGNATURE}")
        self.root.geometry("860x820")
        self.root.minsize(720, 600)
        self.model_cache: Dict[str, whisper.Whisper] = {}
        self.stop_event = threading.Event()
        self.worker_thread: Optional[threading.Thread] = None
        self.tts_stop_event = threading.Event()
        self.tts_worker_thread: Optional[threading.Thread] = None

        self.audio_path_var = tk.StringVar()
        self.model_var = tk.StringVar(value=MODEL_OPTIONS[1])
        self.status_var = tk.StringVar(value="選擇音檔或影片後點擊開始")
        self.output_paths_var = tk.StringVar(value="")
        self.word_timestamps_var = tk.BooleanVar(value=False)
        self.converter_cache: Dict[str, object] = {}
        self.opencc_unavailable_notified = False
        self.edge_tts_unavailable_notified = False
        self.tts_voice_label_var = tk.StringVar(value="台灣女聲・活潑")
        self.tts_rate_var = tk.StringVar(value="+5%")
        self.tts_pitch_var = tk.StringVar(value="+2Hz")
        self.tts_output_path_var = tk.StringVar()
        self.tts_status_var = tk.StringVar(value="貼上文字後點擊產生音檔")
        self.tts_result_var = tk.StringVar(value="")
        self.tts_optimize_var = tk.BooleanVar(value=True)
        self.tts_script_mode_var = tk.StringVar(value="原文直出")
        self.tts_preview_mode_var = tk.StringVar(value="目前輸出預覽")

        self._build_ui()

    def _notify_runtime_warning(self, message: str, *, flag: str) -> None:
        if getattr(self, flag, False):
            return
        setattr(self, flag, True)
        self._update_status(message)
        self.root.after(0, lambda: messagebox.showwarning("提醒", message))

    def _build_ui(self) -> None:
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        self.root.bind_all("<Command-v>", self._handle_global_paste, add="+")
        self.root.bind_all("<Command-V>", self._handle_global_paste, add="+")
        self.root.bind_all("<Control-v>", self._handle_global_paste, add="+")
        self.root.bind_all("<Control-V>", self._handle_global_paste, add="+")
        self.root.bind_all("<Shift-Insert>", self._handle_global_paste, add="+")

        container = ttk.Frame(self.root, padding=16)
        container.grid(row=0, column=0, sticky="nsew")
        container.columnconfigure(0, weight=1)
        container.rowconfigure(0, weight=1)

        notebook = ttk.Notebook(container)
        notebook.grid(row=0, column=0, sticky="nsew")

        transcribe_frame = ttk.Frame(notebook, padding=20)
        transcribe_frame.columnconfigure(1, weight=1)
        transcribe_frame.rowconfigure(7, weight=1)
        notebook.add(transcribe_frame, text="語音轉字幕")
        self._build_transcribe_tab(transcribe_frame)

        tts_outer = ttk.Frame(notebook)
        tts_outer.columnconfigure(0, weight=1)
        tts_outer.rowconfigure(0, weight=1)
        notebook.add(tts_outer, text="文字轉語音")
        self._build_tts_scrollable_tab(tts_outer)

    def _build_tts_scrollable_tab(self, parent: ttk.Frame) -> None:
        canvas = tk.Canvas(parent, highlightthickness=0)
        scrollbar = ttk.Scrollbar(parent, orient="vertical", command=canvas.yview)
        tts_frame = ttk.Frame(canvas, padding=20)

        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.grid(row=0, column=0, sticky="nsew")
        scrollbar.grid(row=0, column=1, sticky="ns")

        window_id = canvas.create_window((0, 0), window=tts_frame, anchor="nw")

        def update_scrollregion(_event=None) -> None:
            canvas.configure(scrollregion=canvas.bbox("all"))

        def resize_inner_frame(event) -> None:
            canvas.itemconfigure(window_id, width=event.width)

        tts_frame.bind("<Configure>", update_scrollregion)
        canvas.bind("<Configure>", resize_inner_frame)

        def on_mousewheel(event) -> str:
            if canvas.winfo_height() >= tts_frame.winfo_reqheight():
                return "break"
            delta = event.delta
            if delta == 0 and getattr(event, "num", None) in (4, 5):
                delta = 120 if event.num == 4 else -120
            if delta:
                canvas.yview_scroll(int(-delta / 120), "units")
            return "break"

        canvas.bind("<MouseWheel>", on_mousewheel)
        canvas.bind("<Button-4>", on_mousewheel)
        canvas.bind("<Button-5>", on_mousewheel)
        tts_frame.bind("<MouseWheel>", on_mousewheel)
        tts_frame.bind("<Button-4>", on_mousewheel)
        tts_frame.bind("<Button-5>", on_mousewheel)

        tts_frame.columnconfigure(1, weight=1)
        tts_frame.rowconfigure(5, weight=1)
        tts_frame.rowconfigure(8, weight=1)
        self._build_tts_tab(tts_frame)

    def _build_transcribe_tab(self, frame: ttk.Frame) -> None:
        frame.columnconfigure(1, weight=1)

        ttk.Label(frame, text="音檔/影片：").grid(row=0, column=0, sticky="w")
        audio_entry = ttk.Entry(frame, textvariable=self.audio_path_var)
        audio_entry.grid(row=0, column=1, sticky="ew", padx=(0, 8))
        ttk.Button(frame, text="瀏覽", command=self.browse_file).grid(
            row=0, column=2, sticky="e"
        )

        ttk.Label(frame, text="Whisper 模型：").grid(
            row=1, column=0, sticky="w", pady=(12, 0)
        )
        model_box = ttk.Combobox(
            frame,
            textvariable=self.model_var,
            values=MODEL_OPTIONS,
            state="readonly",
        )
        model_box.grid(row=1, column=1, sticky="w", pady=(12, 0))

        options_frame = ttk.Labelframe(
            frame,
            text="最佳化選項",
            padding=12,
        )
        options_frame.grid(row=2, column=0, columnspan=3, sticky="ew")
        options_frame.columnconfigure(1, weight=1)

        desc = (
            "預設套用：Temperature=0、關閉跨段上下文、調整靜音門檻。"
            " 如需更細調，可額外輸出字級時間戳。"
        )
        ttk.Label(options_frame, text=desc, wraplength=640, foreground="#444").grid(
            row=0, column=0, columnspan=2, sticky="w", pady=(0, 8)
        )

        ttk.Checkbutton(
            options_frame,
            text="輸出字級時間戳 (word timestamps)",
            variable=self.word_timestamps_var,
        ).grid(row=1, column=0, columnspan=2, sticky="w")

        ttk.Label(
            options_frame,
            text="中文內容會自動轉繁體；外語內容維持原文。",
            foreground="#444",
        ).grid(row=2, column=0, columnspan=2, sticky="w", pady=(8, 0))

        button_row = ttk.Frame(frame)
        button_row.grid(row=3, column=0, columnspan=3, pady=(16, 16), sticky="ew")
        button_row.columnconfigure(0, weight=1)
        button_row.columnconfigure(1, weight=1)
        self.start_button = ttk.Button(button_row, text="開始轉錄", command=self.start_transcription)
        self.start_button.grid(row=0, column=0, sticky="ew", padx=(0, 8))
        self.stop_button = ttk.Button(
            button_row, text="停止", command=self.stop_transcription, state=tk.DISABLED
        )
        self.stop_button.grid(row=0, column=1, sticky="ew")

        ttk.Label(frame, textvariable=self.status_var, foreground="#1c5f2c").grid(
            row=4, column=0, columnspan=3, sticky="w"
        )

        ttk.Label(frame, textvariable=self.output_paths_var, wraplength=640).grid(
            row=5, column=0, columnspan=3, sticky="w", pady=(8, 12)
        )

        ttk.Label(frame, text="轉錄結果預覽：").grid(
            row=6, column=0, columnspan=3, sticky="w"
        )

        self.preview = tk.Text(frame, wrap="word", height=12)
        self.preview.grid(row=7, column=0, columnspan=3, sticky="nsew")
        frame.rowconfigure(7, weight=1)
        self.preview.config(state=tk.DISABLED)

        ttk.Label(
            frame,
            text=f"by {APP_SIGNATURE}",
            foreground="#666",
        ).grid(row=8, column=0, columnspan=2, sticky="w", pady=(8, 0))
        ttk.Button(frame, text="清除", command=self.clear_preview).grid(
            row=8, column=2, sticky="e", pady=(8, 0)
        )

    def _build_tts_tab(self, frame: ttk.Frame) -> None:
        ttk.Label(frame, text="聲音：").grid(row=0, column=0, sticky="w")
        voice_box = ttk.Combobox(
            frame,
            textvariable=self.tts_voice_label_var,
            values=list(TTS_VOICE_OPTIONS.keys()),
            state="readonly",
            width=20,
        )
        voice_box.grid(row=0, column=1, sticky="w")

        controls = ttk.Frame(frame)
        controls.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(12, 0))
        controls.columnconfigure(1, weight=1)
        controls.columnconfigure(3, weight=1)
        controls.columnconfigure(5, weight=1)

        ttk.Label(controls, text="語速：").grid(row=0, column=0, sticky="w")
        ttk.Combobox(
            controls,
            textvariable=self.tts_rate_var,
            values=TTS_RATE_OPTIONS,
            state="readonly",
            width=8,
        ).grid(row=0, column=1, sticky="w", padx=(0, 24))

        ttk.Label(controls, text="音高：").grid(row=0, column=2, sticky="w")
        ttk.Combobox(
            controls,
            textvariable=self.tts_pitch_var,
            values=TTS_PITCH_OPTIONS,
            state="readonly",
            width=8,
        ).grid(row=0, column=3, sticky="w")

        ttk.Label(controls, text="輸出模式：").grid(row=1, column=0, sticky="w", pady=(10, 0))
        ttk.Combobox(
            controls,
            textvariable=self.tts_script_mode_var,
            values=list(TTS_SCRIPT_MODE_TARGETS.keys()),
            state="readonly",
            width=18,
        ).grid(row=1, column=1, sticky="w", pady=(10, 0))

        ttk.Label(frame, text="輸出檔案：").grid(row=2, column=0, sticky="w", pady=(12, 0))
        output_row = ttk.Frame(frame)
        output_row.grid(row=2, column=1, sticky="ew", pady=(12, 0))
        output_row.columnconfigure(0, weight=1)
        ttk.Entry(output_row, textvariable=self.tts_output_path_var).grid(
            row=0, column=0, sticky="ew", padx=(0, 8)
        )
        ttk.Button(output_row, text="選擇", command=self.choose_tts_output_path).grid(
            row=0, column=1, sticky="e"
        )

        ttk.Label(
            frame,
            text="貼上旁白文字後即可輸出 mp3。可保留原文，或先產生 2 分鐘精簡版 / 短影音版，再做朗讀優化。",
            foreground="#444",
            wraplength=700,
        ).grid(row=3, column=0, columnspan=2, sticky="w", pady=(12, 8))

        ttk.Label(frame, text="文字內容：").grid(row=4, column=0, columnspan=2, sticky="w")
        import_row = ttk.Frame(frame)
        import_row.grid(row=4, column=1, sticky="e", pady=(0, 4))
        ttk.Button(import_row, text="匯入文字檔", command=self.import_tts_text_file).grid(
            row=0, column=0, sticky="e"
        )
        ttk.Button(import_row, text="貼上剪貼簿", command=self.paste_tts_text).grid(
            row=0, column=1, sticky="e", padx=(8, 0)
        )
        ttk.Button(import_row, text="清除", command=self.clear_tts_inputs).grid(
            row=0, column=2, sticky="e", padx=(8, 0)
        )
        self.tts_text = tk.Text(frame, wrap="word", height=16)
        self.tts_text.grid(row=5, column=0, columnspan=2, sticky="nsew")
        self._bind_text_shortcuts(self.tts_text)

        optimize_row = ttk.Frame(frame)
        optimize_row.grid(row=6, column=0, columnspan=2, sticky="ew", pady=(10, 0))
        optimize_row.columnconfigure(3, weight=1)
        ttk.Checkbutton(
            optimize_row,
            text="朗讀優化",
            variable=self.tts_optimize_var,
            command=self.refresh_tts_preview,
        ).grid(row=0, column=0, sticky="w")
        ttk.Label(optimize_row, text="預覽模式：").grid(row=0, column=1, sticky="w", padx=(12, 6))
        ttk.Combobox(
            optimize_row,
            textvariable=self.tts_preview_mode_var,
            values=["原文預覽", "目前輸出預覽"],
            state="readonly",
            width=12,
        ).grid(row=0, column=2, sticky="w")
        self.tts_script_mode_var.trace_add("write", lambda *_args: self.refresh_tts_preview())
        self.tts_preview_mode_var.trace_add("write", lambda *_args: self.refresh_tts_preview())
        ttk.Button(optimize_row, text="更新預覽", command=self.refresh_tts_preview).grid(
            row=0, column=3, sticky="e"
        )

        ttk.Label(frame, text="預覽內容：").grid(row=7, column=0, columnspan=2, sticky="w", pady=(10, 0))
        self.tts_preview_text = tk.Text(frame, wrap="word", height=10)
        self.tts_preview_text.grid(row=8, column=0, columnspan=2, sticky="nsew")
        self.tts_preview_text.config(state=tk.DISABLED)

        tts_button_row = ttk.Frame(frame)
        tts_button_row.grid(row=9, column=0, columnspan=2, pady=(16, 12), sticky="ew")
        tts_button_row.columnconfigure(0, weight=1)
        tts_button_row.columnconfigure(1, weight=1)
        self.tts_start_button = ttk.Button(
            tts_button_row, text="產生音檔", command=self.start_tts_generation
        )
        self.tts_start_button.grid(row=0, column=0, sticky="ew", padx=(0, 8))
        self.tts_stop_button = ttk.Button(
            tts_button_row, text="停止", command=self.stop_tts_generation, state=tk.DISABLED
        )
        self.tts_stop_button.grid(row=0, column=1, sticky="ew")

        ttk.Label(frame, textvariable=self.tts_status_var, foreground="#1c5f2c").grid(
            row=10, column=0, columnspan=2, sticky="w"
        )
        ttk.Label(frame, textvariable=self.tts_result_var, wraplength=700).grid(
            row=11, column=0, columnspan=2, sticky="w", pady=(8, 0)
        )
        ttk.Label(
            frame,
            text=f"by {APP_SIGNATURE}",
            foreground="#666",
        ).grid(row=12, column=0, columnspan=2, sticky="w", pady=(12, 0))

    def browse_file(self) -> None:
        path = filedialog.askopenfilename(
            title="選擇音檔或影片",
            filetypes=[
                ("音訊/影片檔案", MEDIA_FILE_PATTERNS),
                ("所有檔案", "*.*"),
            ],
        )
        if path:
            self.audio_path_var.set(path)

    def choose_tts_output_path(self) -> None:
        initial_name = self._default_tts_filename()
        path = filedialog.asksaveasfilename(
            title="選擇輸出音檔位置",
            defaultextension=".mp3",
            initialfile=initial_name,
            filetypes=[("MP3 音檔", "*.mp3")],
        )
        if path:
            self.tts_output_path_var.set(path)

    def import_tts_text_file(self) -> None:
        path = filedialog.askopenfilename(
            title="選擇文字檔",
            filetypes=[
                ("文字檔", "*.txt *.md *.text"),
                ("所有檔案", "*.*"),
            ],
        )
        if not path:
            return
        content: Optional[str] = None
        # 依序嘗試：utf-8-sig（含/不含 BOM 的 UTF-8）→ cp950（台灣繁體 Big5）→ gb18030（簡體）
        for encoding in ("utf-8-sig", "cp950", "gb18030"):
            try:
                with open(path, "r", encoding=encoding, errors="strict") as handle:
                    content = handle.read()
                break
            except (UnicodeDecodeError, LookupError):
                continue
        if content is None:
            messagebox.showerror(
                "錯誤",
                "無法辨識文字檔編碼，請將檔案另存為 UTF-8 格式後再試。",
            )
            return

        self.tts_text.delete("1.0", tk.END)
        self.tts_text.insert("1.0", content)
        self.tts_text.focus_set()
        self._update_tts_status(f"已匯入文字檔：{os.path.basename(path)}")
        self.refresh_tts_preview()

    def start_transcription(self) -> None:
        audio_path = self.audio_path_var.get().strip()
        if not audio_path:
            messagebox.showwarning("提醒", "請先選擇要轉錄的音檔或影片")
            return
        if not os.path.isfile(audio_path):
            messagebox.showerror("錯誤", "找不到指定的檔案，請重新選擇")
            return

        model_name = self.model_var.get()

        if self.worker_thread and self.worker_thread.is_alive():
            messagebox.showinfo("提醒", "目前已經有轉錄正在進行")
            return

        self.stop_event.clear()
        self._update_control_states(True)
        self._update_status("載入模型中（使用 CPU），請稍候...")
        worker = threading.Thread(
            target=self._transcribe_worker,
            args=(audio_path, model_name, self.word_timestamps_var.get()),
            daemon=True,
        )
        self.worker_thread = worker
        worker.start()

    def stop_transcription(self) -> None:
        if not self.worker_thread or not self.worker_thread.is_alive():
            return
        self.stop_event.set()
        self._update_status("已請求停止，將在目前片段完成後停止（大檔案可能需稍等）...")
        self.stop_button.config(state=tk.DISABLED)
        self._interrupt_thread(self.worker_thread)

    def _interrupt_thread(self, thread: threading.Thread, exc_type=SystemExit) -> None:
        ident = thread.ident
        if ident is None:
            return
        result = ctypes.pythonapi.PyThreadState_SetAsyncExc(
            ctypes.c_long(ident), ctypes.py_object(exc_type)
        )
        if result > 1:
            ctypes.pythonapi.PyThreadState_SetAsyncExc(ctypes.c_long(ident), None)

    def _update_control_states(self, running: bool) -> None:
        start_state = tk.DISABLED if running else tk.NORMAL
        stop_state = tk.NORMAL if running else tk.DISABLED
        self.start_button.config(state=start_state)
        self.stop_button.config(state=stop_state)

    def _update_tts_control_states(self, running: bool) -> None:
        start_state = tk.DISABLED if running else tk.NORMAL
        stop_state = tk.NORMAL if running else tk.DISABLED
        self.tts_start_button.config(state=start_state)
        self.tts_stop_button.config(state=stop_state)

    def _update_status(self, message: str) -> None:
        self.root.after(0, lambda: self.status_var.set(message))

    def _update_outputs_label(self, paths: Dict[str, str]) -> None:
        if not paths:
            self.root.after(0, lambda: self.output_paths_var.set(""))
            return
        pretty = "\n".join(f"{kind.upper()}: {path}" for kind, path in paths.items())
        self.root.after(0, lambda: self.output_paths_var.set(pretty))

    def _update_preview(self, text: str) -> None:
        def update() -> None:
            self.preview.config(state=tk.NORMAL)
            self.preview.delete("1.0", tk.END)
            self.preview.insert(tk.END, text.strip() or "(空白)")
            self.preview.config(state=tk.DISABLED)

        self.root.after(0, update)

    def _update_tts_status(self, message: str) -> None:
        self.root.after(0, lambda: self.tts_status_var.set(message))

    def _update_tts_result(self, message: str) -> None:
        self.root.after(0, lambda: self.tts_result_var.set(message))

    def _update_tts_preview(self, text: str) -> None:
        def update() -> None:
            self.tts_preview_text.config(state=tk.NORMAL)
            self.tts_preview_text.delete("1.0", tk.END)
            self.tts_preview_text.insert(tk.END, text.strip() or "(空白)")
            self.tts_preview_text.config(state=tk.DISABLED)

        self.root.after(0, update)

    def _bind_text_shortcuts(self, widget: tk.Text) -> None:
        # 只監聽 <<Paste>> 虛擬事件，不攔截鍵盤快捷鍵。
        # tkinter 原生機制能正確讀取系統剪貼簿（含外部 app 複製的文字），
        # 貼上完成後再補上預覽更新即可。
        widget.bind("<<Paste>>", self._handle_text_paste)

    def _handle_text_paste(self, _event=None) -> None:
        # 不 return "break"，讓原生貼上先執行，10ms 後再更新預覽
        self.root.after(10, self.refresh_tts_preview)

    def _handle_global_paste(self, _event=None) -> str | None:
        target = self.root.focus_get()
        if isinstance(target, tk.Text):
            # 焦點已在文字框，原生 <<Paste>> 會自己處理，不需要干預
            return None
        # 焦點不在文字框時（例如點了其他地方），才手動貼入 tts_text
        self.paste_tts_text()
        return "break"

    def paste_tts_text(self) -> None:
        try:
            clipboard = self.root.clipboard_get()
        except Exception:  # pylint: disable=broad-except
            clipboard = ""
        if not clipboard:
            messagebox.showwarning("提醒", "剪貼簿目前沒有可貼上的文字")
            return

        target = self.root.focus_get()
        if not isinstance(target, tk.Text):
            target = self.tts_text

        try:
            if target.tag_ranges(tk.SEL):
                target.delete(tk.SEL_FIRST, tk.SEL_LAST)
        except tk.TclError:
            pass

        target.insert(tk.INSERT, clipboard)
        target.focus_set()
        self.refresh_tts_preview()

    def _get_model(self, model_name: str) -> whisper.Whisper:
        if model_name not in self.model_cache:
            self._update_status(f"第一次使用 {model_name} 模型（CPU），正在載入...")
            self.model_cache[model_name] = whisper.load_model(model_name, device="cpu")
        return self.model_cache[model_name]

    def _build_options(self, word_timestamps: bool) -> Dict[str, object]:
        opts: Dict[str, object] = dict(DEFAULT_OPTIONS)
        if word_timestamps:
            opts["word_timestamps"] = True
        return opts

    @staticmethod
    def _is_chinese_language(lang: str) -> bool:
        normalized = (lang or "").strip().lower()
        return normalized.startswith("zh") or normalized in {"chinese", "cn"}

    def _to_traditional(self, text: str) -> str:
        if not text:
            return text
        if OpenCC is None:
            self._notify_runtime_warning(
                "未安裝 OpenCC，中文可能維持簡體字型。請先重新執行 01 安裝流程。",
                flag="opencc_unavailable_notified",
            )
            return text
        config = "s2twp"
        converter = self.converter_cache.get(config)
        if converter is None:
            converter = OpenCC(config)
            self.converter_cache[config] = converter
        return converter.convert(text)

    def _normalize_chinese_output(self, result: Dict[str, object]) -> Dict[str, object]:
        detected_lang = str(result.get("language", "") or "")
        if not self._is_chinese_language(detected_lang):
            return result

        converted: Dict[str, object] = dict(result)
        raw_segments = result.get("segments", []) or []
        converted_segments: List[Dict[str, object]] = []

        converted["text"] = self._to_traditional(str(result.get("text", "") or ""))
        for raw_seg in raw_segments:
            if not isinstance(raw_seg, dict):
                continue
            seg = dict(raw_seg)
            seg["text"] = self._to_traditional(str(raw_seg.get("text", "") or ""))
            raw_words = raw_seg.get("words")
            if raw_words:
                converted_words = []
                for raw_word in raw_words:
                    if isinstance(raw_word, dict):
                        w = dict(raw_word)
                        w["word"] = self._to_traditional(str(raw_word.get("word", "") or ""))
                        converted_words.append(w)
                    else:
                        converted_words.append(raw_word)
                seg["words"] = converted_words
            converted_segments.append(seg)
        converted["segments"] = converted_segments
        return converted

    @staticmethod
    def _sanitize_filename(text: str) -> str:
        normalized = re.sub(r"\s+", "_", text.strip())
        normalized = re.sub(r"[^\w\u4e00-\u9fff_-]", "", normalized)
        return normalized[:24] or "tts_output"

    @staticmethod
    def _read_digits(value: str) -> str:
        return "".join(TTS_DIGIT_MAP.get(char, char) for char in value if char.isdigit())

    @staticmethod
    def _format_spoken_hour(hour_text: str, meridiem: str) -> str:
        hour = int(hour_text)
        meridiem = (meridiem or "").strip()

        if meridiem in {"下午", "晚上"} and hour > 12:
            hour -= 12
        elif meridiem == "中午" and hour == 0:
            hour = 12
        elif meridiem == "凌晨" and hour == 12:
            hour = 0

        return f"{hour}點"

    def _spoken_time(self, match: re.Match[str]) -> str:
        start_meridiem = match.group("start_meridiem") or ""
        start_hour = match.group("start_hour")
        start_minute = match.group("start_minute")
        end_meridiem = match.group("end_meridiem") or start_meridiem
        end_hour = match.group("end_hour")
        end_minute = match.group("end_minute")

        start_text = f"{start_meridiem}{self._format_spoken_hour(start_hour, start_meridiem)}"
        if start_minute != "00":
            start_text += f"{int(start_minute)}分"

        if not end_hour:
            return start_text

        end_text = f"{end_meridiem}{self._format_spoken_hour(end_hour, end_meridiem)}"
        if end_minute and end_minute != "00":
            end_text += f"{int(end_minute)}分"
        return f"{start_text}到{end_text}"

    def _spoken_phone(self, match: re.Match[str]) -> str:
        parts = re.split(r"[-\s]+", match.group(0).strip())
        return "，".join(self._read_digits(part) for part in parts if part)

    def _spoken_url(self, match: re.Match[str]) -> str:
        url = match.group(0).strip().rstrip(".,);]")
        spoken = re.sub(r"^https?://", "", url, flags=re.IGNORECASE)
        spoken = spoken.replace("www.", "www ")
        spoken = spoken.replace(".", " 點 ")
        spoken = spoken.replace("/", " slash ")
        spoken = spoken.replace("-", " dash ")
        spoken = spoken.replace("_", " underscore ")
        spoken = spoken.replace("#", " 井號 ")
        spoken = spoken.replace("?", " 問號 ")
        spoken = spoken.replace("=", " 等於 ")
        spoken = spoken.replace("&", " 和 ")
        spoken = re.sub(r'\s+', ' ', spoken).strip()
        return f"網址 {spoken}"

    def _normalize_tts_paragraphs(self, text: str) -> str:
        lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
        paragraphs: List[str] = []
        current: List[str] = []

        for raw_line in lines:
            line = raw_line.strip()
            if not line:
                if current:
                    paragraphs.append(" ".join(current))
                    current = []
                continue
            current.append(line)
        if current:
            paragraphs.append(" ".join(current))

        cleaned = []
        for paragraph in paragraphs:
            paragraph = re.sub(r"[ \t]+", " ", paragraph).strip()
            paragraph = re.sub(r"([。！？!?；;])(?=[^\s\n])", r"\1\n", paragraph)
            paragraph = re.sub(r"([：:])(?!\d)(?=[^\s\n])", r"\1\n", paragraph)
            cleaned.append(paragraph)
        return "\n\n".join(cleaned)

    def _optimize_tts_text(self, text: str) -> str:
        optimized = self._normalize_tts_paragraphs(text)
        optimized = re.sub(
            r"(?<!\w)"
            r"(?P<start_meridiem>凌晨|清晨|早上|上午|中午|下午|晚上)?\s*"
            r"(?P<start_hour>[01]?\d|2[0-3])[:：](?P<start_minute>[0-5]\d)"
            r"(?:\s*[~-]\s*(?P<end_meridiem>凌晨|清晨|早上|上午|中午|下午|晚上)?\s*"
            r"(?P<end_hour>[01]?\d|2[0-3])[:：](?P<end_minute>[0-5]\d))?",
            self._spoken_time,
            optimized,
        )
        optimized = re.sub(
            r"(?:\+886[-\s]?)?(?:0\d{1,2}|9\d{2})[-\s]?\d{3,4}[-\s]?\d{3,4}",
            self._spoken_phone,
            optimized,
        )
        optimized = re.sub(r"https?://\S+|www\.\S+", self._spoken_url, optimized)
        optimized = re.sub(r"\n{3,}", "\n\n", optimized)
        return optimized.strip()

    @staticmethod
    def _split_tts_sentences(text: str) -> List[str]:
        normalized = text.replace("\r\n", "\n").replace("\r", "\n")
        paragraphs = [part.strip() for part in normalized.split("\n") if part.strip()]
        sentences: List[str] = []
        for paragraph in paragraphs:
            parts = [item.strip() for item in re.split(r"(?<=[。！？!?])\s*", paragraph) if item.strip()]
            sentences.extend(parts or [paragraph])
        return sentences

    @staticmethod
    def _extract_chinese_terms(text: str) -> List[str]:
        stop_terms = {
            "我們", "你們", "大家", "這次", "這場", "這個", "這些", "一個", "一起", "可以",
            "如果", "以及", "還有", "不是", "就是", "不只", "現場", "活動", "分享",
        }
        terms = re.findall(r"[\u4e00-\u9fff]{2,6}", text)
        return [term for term in terms if term not in stop_terms]

    def _score_tts_sentence(self, sentence: str, index: int, total: int, term_weights: Dict[str, int]) -> int:
        score = 0
        length = len(sentence)
        if index == 0:
            score += 8
        if index >= max(total - 2, 0):
            score += 5
        if index <= 2:
            score += 2
        if 12 <= length <= 60:
            score += 3
        elif length > 100:
            score -= 2

        strong_patterns = [
            r"\d+月\d+日",
            r"(週|星期)[一二三四五六日天]",
            r"\d+[:：]\d+",
            r"\d+點",
            r"市.+區.+路",
            r"\d+樓",
            r"報名|參加|到場|歡迎|邀請|現場見",
            r"作者|老師|主講|分享",
            r"贈送|送出|加碼|摸彩|抽獎|好禮",
            r"下午茶|晚餐|美食",
        ]
        keyword_patterns = [
            r"活動|講座|商會|分會|旁白",
            r"收穫|驚喜|啟發|成長|突破",
            r"工具|方法|筆記|思維|行動",
        ]
        for pattern in strong_patterns:
            if re.search(pattern, sentence):
                score += 6
        for pattern in keyword_patterns:
            if re.search(pattern, sentence):
                score += 3

        if re.search(r"\d", sentence):
            score += 2

        for term, weight in term_weights.items():
            if term in sentence:
                score += weight
        return score

    def _condense_tts_text(self, text: str, target_chars: int) -> str:
        normalized = self._normalize_tts_paragraphs(text)
        if not normalized:
            return ""
        if len(normalized) <= target_chars:
            return normalized

        sentences = self._split_tts_sentences(normalized)
        if len(sentences) <= 2:
            return normalized[:target_chars].strip()

        term_counts: Dict[str, int] = {}
        for sentence in sentences:
            for term in self._extract_chinese_terms(sentence):
                term_counts[term] = term_counts.get(term, 0) + 1
        term_weights = {
            term: min(count, 3)
            for term, count in term_counts.items()
            if count >= 2
        }

        required_patterns = [
            r"\d+月\d+日|(?:週|星期)[一二三四五六日天]|\d+[:：]\d+|\d+點",
            r"市.+區.+路|\d+樓|地址|地點",
            r"報名|參加|歡迎|邀請|現場見|不要錯過",
        ]

        selected_indexes = set()
        total_length = 0

        for pattern in required_patterns:
            for index, sentence in enumerate(sentences):
                if index in selected_indexes:
                    continue
                if re.search(pattern, sentence):
                    selected_indexes.add(index)
                    total_length += len(sentence)
                    break

        ranked = sorted(
            (
                (
                    self._score_tts_sentence(sentence, index, len(sentences), term_weights),
                    index,
                    sentence,
                )
                for index, sentence in enumerate(sentences)
                if index not in selected_indexes
            ),
            key=lambda item: (-item[0], item[1]),
        )

        min_sentences = 3 if len(sentences) >= 3 else len(sentences)
        soft_limit = int(target_chars * 1.15)
        for _score, index, sentence in ranked:
            need_more_sentences = len(selected_indexes) < min_sentences
            fits_budget = total_length + len(sentence) <= soft_limit
            if need_more_sentences or fits_budget:
                selected_indexes.add(index)
                total_length += len(sentence)

        if not selected_indexes:
            selected_indexes.add(0)

        ordered = sorted(selected_indexes)
        condensed = "\n".join(sentences[index] for index in ordered).strip()

        if len(condensed) > soft_limit:
            trimmed_indexes = ordered[:]
            while len(trimmed_indexes) > min_sentences:
                candidate = trimmed_indexes[-1]
                if re.search(required_patterns[2], sentences[candidate]):
                    break
                trimmed_indexes.pop()
                condensed = "\n".join(sentences[index] for index in trimmed_indexes).strip()
                if len(condensed) <= soft_limit:
                    break
        return condensed

    def _build_tts_script(self, text: str) -> str:
        normalized = self._normalize_tts_paragraphs(text)
        target_chars = TTS_SCRIPT_MODE_TARGETS.get(self.tts_script_mode_var.get())
        if target_chars:
            return self._condense_tts_text(normalized, target_chars)
        return normalized

    def _get_tts_effective_text(self) -> str:
        text = self.tts_text.get("1.0", tk.END).strip()
        if not text:
            return ""
        text = self._build_tts_script(text)
        if self.tts_optimize_var.get():
            return self._optimize_tts_text(text)
        return text

    def refresh_tts_preview(self) -> None:
        source = self.tts_text.get("1.0", tk.END).strip()
        if not source:
            self._update_tts_preview("")
            return
        if self.tts_preview_mode_var.get() == "原文預覽":
            preview_text = source
        else:
            preview_text = self._get_tts_effective_text()
        self._update_tts_preview(preview_text)

    def _default_tts_filename(self) -> str:
        sample = self.tts_text.get("1.0", "2.0").strip() if hasattr(self, "tts_text") else ""
        mode = self.tts_script_mode_var.get()
        suffix_map = {
            "原文直出": "",
            "2 分鐘精簡版": "_2min",
            "短影音版": "_short",
        }
        suffix = suffix_map.get(mode, "")
        return f"{self._sanitize_filename(sample)}{suffix}.mp3"

    def _get_tts_output_path(self) -> str:
        current = self.tts_output_path_var.get().strip()
        if current:
            return current
        default_name = self._default_tts_filename()
        desktop = os.path.expanduser("~/Desktop")
        base_dir = desktop if os.path.isdir(desktop) else os.getcwd()
        return os.path.join(base_dir, default_name)

    @staticmethod
    def _chunk_tts_text(text: str, max_chars: int = TTS_MAX_CHARS) -> List[str]:
        paragraphs = [part.strip() for part in text.splitlines() if part.strip()]
        chunks: List[str] = []
        current = ""

        def push(value: str) -> None:
            value = value.strip()
            if value:
                chunks.append(value)

        for paragraph in paragraphs:
            sentences = [s.strip() for s in re.split(r"(?<=[。！？!?])", paragraph) if s.strip()]
            for sentence in sentences or [paragraph]:
                if len(sentence) > max_chars:
                    pieces = [sentence[i : i + max_chars] for i in range(0, len(sentence), max_chars)]
                else:
                    pieces = [sentence]
                for piece in pieces:
                    candidate = f"{current}\n{piece}".strip() if current else piece
                    if len(candidate) <= max_chars:
                        current = candidate
                    else:
                        push(current)
                        current = piece
            if current:
                push(current)
                current = ""
        push(current)
        result_chunks = [c for c in chunks if c] or [text.strip()]
        return [c for c in result_chunks if c]

    def _ensure_tts_dependency(self) -> bool:
        if edge_tts is not None:
            return True
        self._notify_runtime_warning(
            "未安裝 edge-tts，請先重新執行 01 安裝流程後再使用文字轉語音。",
            flag="edge_tts_unavailable_notified",
        )
        return False

    def start_tts_generation(self) -> None:
        text = self._get_tts_effective_text()
        if not text:
            messagebox.showwarning("提醒", "請先貼上要轉成語音的文字內容")
            return
        if not self._ensure_tts_dependency():
            return
        if self.tts_worker_thread and self.tts_worker_thread.is_alive():
            messagebox.showinfo("提醒", "目前已經有文字轉語音正在進行")
            return

        output_path = self._get_tts_output_path()
        if os.path.exists(output_path):
            overwrite = messagebox.askyesno(
                "檔案已存在",
                f"輸出檔案已存在：\n{output_path}\n\n是否覆蓋？",
            )
            if not overwrite:
                return
        self.tts_output_path_var.set(output_path)
        self.tts_stop_event.clear()
        self._update_tts_control_states(True)
        self._update_tts_status("準備產生音檔...")
        self._update_tts_result("")
        worker = threading.Thread(
            target=self._tts_worker,
            args=(
                text,
                TTS_VOICE_OPTIONS[self.tts_voice_label_var.get()],
                self.tts_rate_var.get(),
                self.tts_pitch_var.get(),
                output_path,
            ),
            daemon=True,
        )
        self.tts_worker_thread = worker
        worker.start()

    def stop_tts_generation(self) -> None:
        if not self.tts_worker_thread or not self.tts_worker_thread.is_alive():
            return
        self.tts_stop_event.set()
        self._update_tts_status("停止中，請稍候...")
        self.tts_stop_button.config(state=tk.DISABLED)

    async def _save_tts_chunk(self, text: str, voice: str, rate: str, pitch: str, output_path: str) -> None:
        communicator = edge_tts.Communicate(text, voice=voice, rate=rate, pitch=pitch)
        await communicator.save(output_path)

    async def _run_tts_chunks(
        self,
        chunks: List[str],
        voice: str,
        rate: str,
        pitch: str,
        temp_dir: str,
    ) -> List[str]:
        """依序合成各分段，每 0.1 秒檢查停止事件，可即時取消。"""
        chunk_paths: List[str] = []
        for index, chunk in enumerate(chunks, start=1):
            if self.tts_stop_event.is_set():
                raise SystemExit
            chunk_path = os.path.join(temp_dir, f"{index:03d}.mp3")
            self._update_tts_status(f"正在合成第 {index}/{len(chunks)} 段...")
            task = asyncio.ensure_future(
                self._save_tts_chunk(chunk, voice, rate, pitch, chunk_path)
            )
            while not task.done():
                await asyncio.sleep(0.1)
                if self.tts_stop_event.is_set():
                    task.cancel()
                    try:
                        await task
                    except asyncio.CancelledError:
                        pass
                    except Exception:
                        pass  # 取消時忽略 edge-tts 中途中斷的例外
                    raise SystemExit
            await task  # 傳遞 edge-tts 本身的例外
            chunk_paths.append(chunk_path)
        return chunk_paths

    def _find_ffmpeg(self) -> Optional[str]:
        local = os.path.join(os.path.dirname(__file__), "ffmpeg")
        if os.path.isfile(local):
            return local
        return shutil.which("ffmpeg")

    def _concat_mp3_chunks(self, chunk_paths: List[str], output_path: str) -> None:
        ffmpeg_path = self._find_ffmpeg()
        if ffmpeg_path is None:
            raise RuntimeError("找不到 ffmpeg，無法合併分段音檔。")

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".txt", encoding="utf-8", delete=False
        ) as concat_handle:
            concat_file = concat_handle.name
            for chunk_path in chunk_paths:
                escaped = chunk_path.replace("'", "'\\''")
                concat_handle.write(f"file '{escaped}'\n")
        try:
            subprocess.run(
                [
                    ffmpeg_path,
                    "-y",
                    "-f", "concat",
                    "-safe", "0",
                    "-i", concat_file,
                    "-c", "copy",
                    output_path,
                ],
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        finally:
            if os.path.exists(concat_file):
                os.remove(concat_file)

    def _tts_worker(self, text: str, voice: str, rate: str, pitch: str, output_path: str) -> None:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            chunks = self._chunk_tts_text(text)
            os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
            self._update_tts_status(f"開始合成，共 {len(chunks)} 段...")

            with tempfile.TemporaryDirectory(prefix="whisper_tts_") as temp_dir:
                chunk_paths = loop.run_until_complete(
                    self._run_tts_chunks(chunks, voice, rate, pitch, temp_dir)
                )
                if len(chunk_paths) == 1:
                    shutil.copyfile(chunk_paths[0], output_path)
                else:
                    self._update_tts_status("正在合併分段音檔...")
                    self._concat_mp3_chunks(chunk_paths, output_path)

            self._update_tts_status("完成！音檔已產生。")
            self._update_tts_result(f"MP3: {output_path}")
        except SystemExit:
            self._update_tts_status("文字轉語音已停止。")
            self._update_tts_result("")
        except Exception as exc:  # pylint: disable=broad-except
            self._update_tts_status("文字轉語音失敗，請稍後再試")
            self._update_tts_result("")
            message = str(exc)
            self.root.after(0, lambda: messagebox.showerror("錯誤", message))
        finally:
            loop.close()
            self.tts_worker_thread = None
            self.tts_stop_event.clear()
            # 完成後清空路徑，下次會重新根據內容產生新檔名，避免靜默覆蓋
            self.root.after(0, lambda: self.tts_output_path_var.set(""))
            self.root.after(0, lambda: self._update_tts_control_states(False))

    def _transcribe_worker(
        self, audio_path: str, model_name: str, word_timestamps: bool
    ) -> None:
        try:
            model = self._get_model(model_name)
            self._update_status("轉錄中（使用 CPU），處理時間取決於檔案長度與模型大小...")
            options = self._build_options(word_timestamps)
            raw_result = model.transcribe(audio_path, fp16=False, verbose=False, **options)
            result = self._normalize_chinese_output(raw_result)
            if self.stop_event.is_set():
                raise SystemExit

            text = result.get("text", "").strip()
            if self.stop_event.is_set():
                raise SystemExit

            output_paths = self._write_outputs(audio_path, result)
            detected_lang = result.get("language") or "unknown"
            self._update_status(
                f"完成！偵測語言：{detected_lang}. 檔案已產生。"
            )
            self._update_outputs_label(output_paths)
            self._update_preview(text)
        except SystemExit:
            self._update_status("轉錄已停止。")
            self._update_outputs_label({})
            self._update_preview("")
        except Exception as exc:  # pylint: disable=broad-except
            self._handle_error(exc)
        finally:
            self.worker_thread = None
            self.stop_event.clear()
            self.root.after(0, lambda: self._update_control_states(False))

    def _write_outputs(
        self, audio_path: str, result: Dict[str, object]
    ) -> Dict[str, str]:
        base_dir = os.path.dirname(audio_path)
        audio_name = os.path.splitext(os.path.basename(audio_path))[0]
        detected_lang = str(result.get("language", "") or "").lower() or "auto"
        suffix = detected_lang

        text_path = os.path.join(base_dir, f"{audio_name}_{suffix}.txt")
        with open(text_path, "w", encoding="utf-8") as txt_file:
            txt_file.write(result.get("text", "").strip() + "\n")

        segments = result.get("segments", []) or []
        srt_content = _format_srt(segments)
        srt_path = os.path.join(base_dir, f"{audio_name}_{suffix}.srt")
        with open(srt_path, "w", encoding="utf-8") as srt_file:
            srt_file.write(srt_content)

        vtt_content = _format_vtt(segments)
        vtt_path = os.path.join(base_dir, f"{audio_name}_{suffix}.vtt")
        with open(vtt_path, "w", encoding="utf-8") as vtt_file:
            vtt_file.write(vtt_content)

        return {"txt": text_path, "srt": srt_path, "vtt": vtt_path}

    def _handle_error(self, exc: Exception) -> None:
        self._update_status("發生錯誤，請稍後再試")
        self._update_outputs_label({})
        self._update_preview("")
        message = str(exc)
        self.root.after(0, lambda: messagebox.showerror("錯誤", message))

    def clear_preview(self) -> None:
        self.preview.config(state=tk.NORMAL)
        self.preview.delete("1.0", tk.END)
        self.preview.config(state=tk.DISABLED)
        self.output_paths_var.set("")
        self.status_var.set("已清除結果，可重新選擇音檔或影片")

    def clear_tts_inputs(self) -> None:
        self.tts_text.delete("1.0", tk.END)
        self.tts_output_path_var.set("")
        self.tts_result_var.set("")
        self.tts_status_var.set("已清除內容，可重新貼上文字產生音檔")
        self._update_tts_preview("")


def main() -> None:
    root = tk.Tk()
    WhisperApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
