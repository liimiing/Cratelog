#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")"
export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"
if [[ ! -x .venv-macos/bin/python ]]; then
    echo '请先运行 bash install_macos.sh'; exit 1
fi
exec .venv-macos/bin/python cratelog.py
