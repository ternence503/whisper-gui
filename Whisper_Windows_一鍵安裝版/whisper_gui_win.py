#!/usr/bin/env python3
"""Whisper Windows 圖形介面工具。"""

from __future__ import annotations

import ctypes
import io
import os
import sys
import threading
from typing import Dict, Iterable, List, Optional

try:
    import tkinter as tk
    from tkinter import filedialog, messagebox, ttk
except ModuleNotFoundError as exc:
    raise SystemExit("目前 Python 缺少 tkinter，請重新安裝 Python 後再執行。") from exc

import whisper
try:
    from opencc import OpenCC
except Exception:  # pragma: no cover
    OpenCC = None

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
APP_VERSION = "v1.1.0"
APP_SIGNATURE = f"{APP_AUTHOR} {APP_VERSION}"

DEFAULT_OPTIONS = {
    "temperature": 0.0,
    "condition_on_previous_text": False,
    "no_speech_threshold": 0.4,
    "compression_ratio_threshold": 2.0,
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


def _format_timestamp(seconds: float, *, separator: str) -> str:
    if seconds is None:
        seconds = 0.0
    milliseconds = round(float(seconds) * 1000)
    total_seconds, ms = divmod(milliseconds, 1000)
    minutes, sec = divmod(total_seconds, 60)
    hours, minutes = divmod(minutes, 60)
    if separator == ",":
        return f"{hours:02}:{minutes:02}:{sec:02},{ms:03}"
    return f"{hours:02}:{minutes:02}:{sec:02}.{ms:03}"


def _format_srt(segments: Iterable[Dict[str, float]]) -> str:
    lines: List[str] = []
    index = 1
    for segment in segments:
        text = segment.get("text", "").strip()
        if not text:
            continue
        start = _format_timestamp(segment.get("start", 0.0), separator=",")
        end = _format_timestamp(segment.get("end", 0.0), separator=",")
        lines.append(str(index))
        lines.append(f"{start} --> {end}")
        lines.append(text)
        lines.append("")
        index += 1
    return "\n".join(lines).strip() + "\n"


def _format_vtt(segments: Iterable[Dict[str, float]]) -> str:
    lines: List[str] = ["WEBVTT", ""]
    for segment in segments:
        text = segment.get("text", "").strip()
        if not text:
            continue
        start = _format_timestamp(segment.get("start", 0.0), separator=".")
        end = _format_timestamp(segment.get("end", 0.0), separator=".")
        lines.append(f"{start} --> {end}")
        lines.append(text)
        lines.append("")
    return "\n".join(lines).strip() + "\n"


def _configure_runtime_environment() -> None:
    app_dir = os.path.dirname(sys.executable if getattr(sys, "frozen", False) else os.path.abspath(__file__))
    ffmpeg_paths = [
        app_dir,
        os.path.join(app_dir, "ffmpeg"),
    ]

    for directory in ffmpeg_paths:
        ffmpeg_exe = os.path.join(directory, "ffmpeg.exe")
        ffprobe_exe = os.path.join(directory, "ffprobe.exe")
        if os.path.isfile(ffmpeg_exe) and os.path.isfile(ffprobe_exe):
            current_path = os.environ.get("PATH", "")
            path_items = current_path.split(os.pathsep) if current_path else []
            if directory not in path_items:
                os.environ["PATH"] = os.pathsep.join([directory, current_path]) if current_path else directory
            break

    model_dir = os.path.join(app_dir, "models")
    if os.path.isdir(model_dir):
        os.environ.setdefault("WHISPER_MODEL_DIR", model_dir)


_configure_runtime_environment()
_ensure_stdio()


class WhisperApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title(f"Whisper 語音轉文字 | {APP_SIGNATURE}")
        self.root.geometry("760x580")
        self.model_cache: Dict[str, whisper.Whisper] = {}
        self.stop_event = threading.Event()
        self.worker_thread: Optional[threading.Thread] = None

        self.audio_path_var = tk.StringVar()
        self.model_var = tk.StringVar(value="small")
        self.status_var = tk.StringVar(value="請先選擇音檔或影片，再按開始轉錄。")
        self.output_paths_var = tk.StringVar(value="")
        self.word_timestamps_var = tk.BooleanVar(value=False)
        self.converter_cache: Dict[str, object] = {}
        self.opencc_unavailable_notified = False

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

        frame = ttk.Frame(self.root, padding=20)
        frame.grid(row=0, column=0, sticky="nsew")
        frame.columnconfigure(1, weight=1)

        ttk.Label(frame, text="音檔/影片：").grid(row=0, column=0, sticky="w")
        entry = ttk.Entry(frame, textvariable=self.audio_path_var)
        entry.grid(row=0, column=1, sticky="ew", padx=(0, 8))
        ttk.Button(frame, text="瀏覽", command=self.browse_file).grid(row=0, column=2, sticky="e")

        ttk.Label(frame, text="模型：").grid(row=1, column=0, sticky="w", pady=(12, 0))
        combo = ttk.Combobox(frame, textvariable=self.model_var, values=MODEL_OPTIONS, state="readonly")
        combo.grid(row=1, column=1, sticky="w", pady=(12, 0))

        options = ttk.Labelframe(frame, text="選項", padding=12)
        options.grid(row=2, column=0, columnspan=3, sticky="ew", pady=(12, 0))

        ttk.Label(
            options,
            text="已套用新手預設（CPU 模式）。",
            foreground="#444",
        ).grid(row=0, column=0, sticky="w")

        ttk.Checkbutton(
            options,
            text="輸出字級時間戳（word timestamps）",
            variable=self.word_timestamps_var,
        ).grid(row=1, column=0, sticky="w", pady=(6, 0))

        ttk.Label(
            options,
            text="中文內容會自動轉繁體；外語內容維持原文。",
            foreground="#444",
        ).grid(row=2, column=0, sticky="w", pady=(8, 0))

        button_row = ttk.Frame(frame)
        button_row.grid(row=3, column=0, columnspan=3, sticky="ew", pady=(16, 12))
        button_row.columnconfigure(0, weight=1)
        button_row.columnconfigure(1, weight=1)

        self.start_button = ttk.Button(button_row, text="開始轉錄", command=self.start_transcription)
        self.start_button.grid(row=0, column=0, sticky="ew", padx=(0, 8))
        self.stop_button = ttk.Button(
            button_row,
            text="停止",
            command=self.stop_transcription,
            state=tk.DISABLED,
        )
        self.stop_button.grid(row=0, column=1, sticky="ew")

        ttk.Label(frame, textvariable=self.status_var, foreground="#1c5f2c").grid(
            row=4, column=0, columnspan=3, sticky="w"
        )

        ttk.Label(frame, textvariable=self.output_paths_var, wraplength=700).grid(
            row=5, column=0, columnspan=3, sticky="w", pady=(8, 12)
        )

        ttk.Label(frame, text="結果預覽：").grid(row=6, column=0, columnspan=3, sticky="w")
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

    def start_transcription(self) -> None:
        audio_path = self.audio_path_var.get().strip()
        if not audio_path:
            messagebox.showwarning("提醒", "請先選擇音檔或影片。")
            return
        if not os.path.isfile(audio_path):
            messagebox.showerror("錯誤", "找不到檔案，請重新選擇。")
            return

        model_name = self.model_var.get().strip() or "small"
        if self.worker_thread and self.worker_thread.is_alive():
            messagebox.showinfo("提醒", "目前已有轉錄進行中。")
            return

        self.stop_event.clear()
        self._update_control_states(True)
        self._update_status("正在載入模型（CPU）...")
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
        self.start_button.config(state=tk.DISABLED if running else tk.NORMAL)
        self.stop_button.config(state=tk.NORMAL if running else tk.DISABLED)

    def _update_status(self, message: str) -> None:
        self.root.after(0, lambda: self.status_var.set(message))

    def _update_outputs_label(self, paths: Dict[str, str]) -> None:
        if not paths:
            self.root.after(0, lambda: self.output_paths_var.set(""))
            return
        pretty = "\n".join(f"{kind.upper()}: {path}" for kind, path in paths.items())
        self.root.after(0, lambda: self.output_paths_var.set(pretty))

    def _update_preview(self, text: str) -> None:
        def do_update() -> None:
            self.preview.config(state=tk.NORMAL)
            self.preview.delete("1.0", tk.END)
            self.preview.insert(tk.END, text.strip() or "(空白)")
            self.preview.config(state=tk.DISABLED)

        self.root.after(0, do_update)

    def _get_model(self, model_name: str) -> whisper.Whisper:
        if model_name not in self.model_cache:
            self._update_status(f"首次使用模型 {model_name}，載入中...")
            self.model_cache[model_name] = whisper.load_model(model_name, device="cpu")
        return self.model_cache[model_name]

    def _build_options(self, word_timestamps: bool) -> Dict[str, object]:
        options: Dict[str, object] = dict(DEFAULT_OPTIONS)
        if word_timestamps:
            options["word_timestamps"] = True
        return options

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

    def _transcribe_worker(
        self,
        audio_path: str,
        model_name: str,
        word_timestamps: bool,
    ) -> None:
        try:
            model = self._get_model(model_name)
            self._update_status("轉錄中，時間會依檔案長度與模型大小而定...")
            options = self._build_options(word_timestamps)
            raw_result = model.transcribe(audio_path, fp16=False, verbose=False, **options)
            result = self._normalize_chinese_output(raw_result)
            if self.stop_event.is_set():
                raise SystemExit

            text = str(result.get("text", "")).strip()
            if self.stop_event.is_set():
                raise SystemExit

            output_paths = self._write_outputs(audio_path, result)
            detected_lang = result.get("language", "?")
            self._update_status(f"完成！偵測語言：{detected_lang}")
            self._update_outputs_label(output_paths)
            self._update_preview(text)
        except SystemExit:
            self._update_status("已停止轉錄。")
            self._update_outputs_label({})
            self._update_preview("")
        except Exception as exc:  # pylint: disable=broad-except
            self._handle_error(exc)
        finally:
            self.worker_thread = None
            self.stop_event.clear()
            self.root.after(0, lambda: self._update_control_states(False))

    def _write_outputs(self, audio_path: str, result: Dict[str, object]) -> Dict[str, str]:
        base_dir = os.path.dirname(audio_path)
        audio_name = os.path.splitext(os.path.basename(audio_path))[0]
        detected_lang = str(result.get("language", "") or "").lower() or "auto"
        suffix = detected_lang

        txt_path = os.path.join(base_dir, f"{audio_name}_{suffix}.txt")
        with open(txt_path, "w", encoding="utf-8") as file_obj:
            file_obj.write(str(result.get("text", "")).strip() + "\n")

        segments = result.get("segments", []) or []
        srt_path = os.path.join(base_dir, f"{audio_name}_{suffix}.srt")
        with open(srt_path, "w", encoding="utf-8") as file_obj:
            file_obj.write(_format_srt(segments))

        vtt_path = os.path.join(base_dir, f"{audio_name}_{suffix}.vtt")
        with open(vtt_path, "w", encoding="utf-8") as file_obj:
            file_obj.write(_format_vtt(segments))

        return {
            "txt": txt_path,
            "srt": srt_path,
            "vtt": vtt_path,
        }

    def _handle_error(self, exc: Exception) -> None:
        self._update_status("發生錯誤，請查看訊息。")
        self._update_outputs_label({})
        self._update_preview("")
        message = str(exc)
        self.root.after(0, lambda: messagebox.showerror("錯誤", message))

    def clear_preview(self) -> None:
        self.preview.config(state=tk.NORMAL)
        self.preview.delete("1.0", tk.END)
        self.preview.config(state=tk.DISABLED)
        self.output_paths_var.set("")
        self.status_var.set("已清除，可重新轉錄。")


def main() -> None:
    root = tk.Tk()
    WhisperApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
