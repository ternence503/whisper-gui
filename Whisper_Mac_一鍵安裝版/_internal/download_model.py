#!/usr/bin/env python3
"""下載 Whisper 模型到本地資料夾。"""

from __future__ import annotations

import argparse
import pathlib
import urllib.request

try:
    from whisper import _MODELS  # type: ignore
except Exception as exc:  # pragma: no cover
    raise SystemExit("尚未安裝 openai-whisper，請先執行一鍵安裝腳本。") from exc


def download_model(name: str, output_dir: pathlib.Path) -> pathlib.Path:
    if name not in _MODELS:
        choices = ", ".join(sorted(_MODELS))
        raise SystemExit(f"模型 '{name}' 不存在，可用模型：{choices}")

    url = _MODELS[name]
    output_dir.mkdir(parents=True, exist_ok=True)
    target = output_dir / pathlib.Path(url).name

    if target.exists():
        print(f"模型已存在：{target.name}")
        return target

    print(f"下載模型 {name} -> {target}")
    with urllib.request.urlopen(url) as src, open(target, "wb") as dst:
        while True:
            chunk = src.read(1024 * 1024)
            if not chunk:
                break
            dst.write(chunk)

    print("模型下載完成")
    return target


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("model", help="模型名稱，例如 small / medium / large / turbo")
    parser.add_argument("--output", "-o", default="models", help="輸出資料夾，預設 models")
    args = parser.parse_args()

    output = pathlib.Path(args.output).resolve()
    download_model(args.model, output)


if __name__ == "__main__":
    main()
