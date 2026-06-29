#!/usr/bin/env python3
"""Download a Whisper model into a local folder for offline reuse."""

from __future__ import annotations

import argparse
import pathlib
import urllib.request

try:
    # Use the OS trust store for SSL verification (same behavior as a browser).
    # Fixes CERTIFICATE_VERIFY_FAILED when a corporate firewall/antivirus does
    # SSL inspection with a self-signed root that the OS trusts but Python doesn't.
    import truststore

    truststore.inject_into_ssl()
except Exception:  # pragma: no cover
    pass

try:
    from whisper import _MODELS  # type: ignore
except Exception as exc:  # pragma: no cover
    raise SystemExit("openai-whisper is not installed in this Python environment.") from exc


def download_model(name: str, output_dir: pathlib.Path) -> pathlib.Path:
    if name not in _MODELS:
        choices = ", ".join(sorted(_MODELS))
        raise SystemExit(f"Unknown model '{name}'. Available: {choices}")

    url = _MODELS[name]
    output_dir.mkdir(parents=True, exist_ok=True)
    target = output_dir / pathlib.Path(url).name
    if target.exists():
        print(f"Model already exists: {target.name}")
        return target

    print(f"Downloading model '{name}' to {target}")
    with urllib.request.urlopen(url) as source, open(target, "wb") as sink:
        while True:
            chunk = source.read(1024 * 1024)
            if not chunk:
                break
            sink.write(chunk)
    print("Model download complete.")
    return target


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("model", help="Model name: tiny/base/small/medium/large/turbo")
    parser.add_argument(
        "--output",
        "-o",
        default="models",
        help="Output directory (default: models)",
    )
    args = parser.parse_args()

    output = pathlib.Path(args.output).resolve()
    download_model(args.model, output)


if __name__ == "__main__":
    main()
