#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")"
if [[ "$(uname -s)" != Darwin ]]; then echo '此脚本用于 macOS。'; exit 1; fi
if ! command -v brew >/dev/null 2>&1; then
    for candidate in /opt/homebrew/bin/brew /usr/local/bin/brew; do
        if [[ -x "$candidate" ]]; then eval "$("$candidate" shellenv)"; break; fi
    done
fi
if ! command -v brew >/dev/null 2>&1; then
    echo '请先从 https://brew.sh 安装 Homebrew，再运行本脚本。'; exit 1
fi
if ! xcrun --find clang >/dev/null 2>&1; then
    xcode-select --install || true
    echo 'Finish Command Line Tools installation, then run this installer again.'; exit 1
fi
brew install python@3.14 python-tk@3.14 mpv ffmpeg pkg-config
CRATELOG_PY="$(brew --prefix python@3.14)/bin/python3.14"
"$CRATELOG_PY" -c 'import tkinter, _tkinter; print("Tk", tkinter.TkVersion)'
if [[ -e .venv-macos ]]; then
    if ! .venv-macos/bin/python -c 'import sys, tkinter; assert sys.version_info[:2] == (3,14)' >/dev/null 2>&1; then
        echo '.venv-macos 无法使用，请先将其改名备份，再运行安装脚本。'; exit 1
    fi
else
    "$CRATELOG_PY" -m venv .venv-macos
fi
.venv-macos/bin/python -m pip install --upgrade pip
.venv-macos/bin/python -m pip install --upgrade -r requirements.txt
bash tools/build_macos.sh
if [[ "${CI:-}" == true ]]; then
    .venv-macos/bin/python tools/check_install.py
else
    .venv-macos/bin/python tools/check_install.py --playback
fi
 # Optional native acceptance: .venv-macos/bin/python tools/check_macos_render.py
.venv-macos/bin/python tools/create_macos_app.py
echo '安装检查通过。双击项目目录内 Cratelog.app 启动；终端排错：bash start_macos.command'
