#!/bin/bash
set -euo pipefail

MODEL="small"
ONLY_LAUNCH=0

if [[ "${1:-}" == "--only-launch" ]]; then
  ONLY_LAUNCH=1
  shift
fi

if [[ -n "${1:-}" ]]; then
  MODEL="$1"
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$SCRIPT_DIR/.venv"
VENV_PYTHON="$VENV_DIR/bin/python"
DEPS_STAMP="$VENV_DIR/.deps_ready"
REQUIREMENTS_FILE="$SCRIPT_DIR/requirements-mac.txt"
GUI_SCRIPT="$SCRIPT_DIR/whisper_gui_mac.py"
MODEL_DOWNLOADER="$SCRIPT_DIR/download_model.py"
MODELS_DIR="$SCRIPT_DIR/models"

log_step() {
  echo "[Whisper Mac] $1"
}

ensure_brew_in_path() {
  if command -v brew >/dev/null 2>&1; then
    return
  fi
  if [[ -x /opt/homebrew/bin/brew ]]; then
    eval "$(/opt/homebrew/bin/brew shellenv)"
    return
  fi
  if [[ -x /usr/local/bin/brew ]]; then
    eval "$(/usr/local/bin/brew shellenv)"
  fi
}

ensure_homebrew() {
  ensure_brew_in_path
  if command -v brew >/dev/null 2>&1; then
    return
  fi

  log_step "未偵測到 Homebrew，開始安裝（可能要求輸入密碼）..."
  NONINTERACTIVE=1 /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
  ensure_brew_in_path

  if ! command -v brew >/dev/null 2>&1; then
    echo "錯誤：Homebrew 安裝失敗，請先手動安裝後再重試。"
    exit 1
  fi
}

ensure_formula() {
  local formula="$1"
  if brew list --versions "$formula" >/dev/null 2>&1; then
    return
  fi

  log_step "安裝 $formula ..."
  brew install "$formula"
}

resolve_base_python() {
  ensure_brew_in_path
  if command -v python3.12 >/dev/null 2>&1; then
    command -v python3.12
    return
  fi

  local brew_python=""
  brew_python="$(brew --prefix python@3.12 2>/dev/null || true)"
  if [[ -n "$brew_python" && -x "$brew_python/bin/python3.12" ]]; then
    echo "$brew_python/bin/python3.12"
    return
  fi

  if command -v python3 >/dev/null 2>&1; then
    command -v python3
    return
  fi
}

ensure_python_version() {
  local python_exe="$1"
  if ! "$python_exe" - <<'PY' >/dev/null 2>&1
import sys
sys.exit(0 if sys.version_info >= (3, 9) else 1)
PY
  then
    echo "錯誤：需要 Python 3.9+，目前版本不符合。"
    exit 1
  fi
}

ensure_runtime_dependencies() {
  ensure_homebrew
  ensure_formula "tcl-tk"
  ensure_formula "python@3.12"
  ensure_formula "ffmpeg"
}

ensure_venv_and_packages() {
  local base_python="$1"
  local needs_install=0

  if [[ ! -x "$VENV_PYTHON" ]]; then
    log_step "建立本地虛擬環境..."
    "$base_python" -m venv "$VENV_DIR"
  fi

  if [[ ! -f "$DEPS_STAMP" ]]; then
    needs_install=1
  fi
  if [[ "$needs_install" -eq 0 ]]; then
    if ! "$VENV_PYTHON" -c "import opencc" >/dev/null 2>&1; then
      needs_install=1
    fi
  fi
  if [[ "$needs_install" -eq 0 ]]; then
    if ! "$VENV_PYTHON" -c "import edge_tts" >/dev/null 2>&1; then
      needs_install=1
    fi
  fi

  if [[ "$needs_install" -eq 1 ]]; then
    log_step "安裝/更新 Python 套件..."
    "$VENV_PYTHON" -m pip install --upgrade pip setuptools wheel
    "$VENV_PYTHON" -m pip install -r "$REQUIREMENTS_FILE"
    touch "$DEPS_STAMP"
  fi
}

ensure_model() {
  mkdir -p "$MODELS_DIR"
  log_step "準備 Whisper 模型：$MODEL"
  "$VENV_PYTHON" "$MODEL_DOWNLOADER" "$MODEL" --output "$MODELS_DIR"
}

launch_gui() {
  if [[ ! -x "$VENV_PYTHON" ]]; then
    echo "錯誤：找不到虛擬環境，請先執行 01-一鍵安裝並啟動.command。"
    exit 1
  fi

  ensure_brew_in_path
  export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"
  export WHISPER_MODEL_DIR="$MODELS_DIR"

  log_step "啟動 Whisper GUI..."
  exec "$VENV_PYTHON" "$GUI_SCRIPT"
}

if [[ "$ONLY_LAUNCH" -eq 0 ]]; then
  MODEL_FILE="$MODELS_DIR/$MODEL.pt"
  ALREADY_INSTALLED=0
  if [[ -f "$DEPS_STAMP" && -f "$MODEL_FILE" ]] && command -v ffmpeg >/dev/null 2>&1; then
    ALREADY_INSTALLED=1
  fi

  if [[ "$ALREADY_INSTALLED" -eq 1 ]]; then
    echo ""
    echo "環境已就緒，正在啟動程式..."
    echo ""
  else
    echo ""
    echo "首次安裝，請稍候..."
    echo "（需安裝 Homebrew、Python、ffmpeg 與 Whisper 模型，約需幾分鐘，請保持網路連線）"
    echo ""

    echo "[步驟 1/3] 安裝 Homebrew、Python 3.12、ffmpeg..."
    ensure_runtime_dependencies
    BASE_PYTHON="$(resolve_base_python)"
    if [[ -z "${BASE_PYTHON:-}" || ! -x "$BASE_PYTHON" ]]; then
      echo "錯誤：找不到可用的 python3。"
      exit 1
    fi
    ensure_python_version "$BASE_PYTHON"

    echo "[步驟 2/3] 安裝 Python 套件（含 openai-whisper，請耐心等候）..."
    ensure_venv_and_packages "$BASE_PYTHON"

    echo "[步驟 3/3] 下載 Whisper 語音模型 (${MODEL})..."
    ensure_model

    echo ""
    echo "====================================="
    echo "  安裝完成！程式即將自動開啟。"
    echo "  下次只需雙擊「02-直接啟動.command」即可。"
    echo "====================================="
    echo ""
  fi
fi

launch_gui
