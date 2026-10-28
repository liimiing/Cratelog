#!/bin/bash
cd "$(dirname "$0")" || exit 1
bash install_macos.sh
status=$?
read -r -p "Press Return to close / 按回车关闭"
exit "$status"
