#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")"
if [[ ! -x .venv-macos/bin/python ]]; then echo 'Run install_macos.command first.'; exit 1; fi
.venv-macos/bin/python -m pip install -r requirements-build.txt
bash tools/build_macos.sh
.venv-macos/bin/python tools/build_release.py
