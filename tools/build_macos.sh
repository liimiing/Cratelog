#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")/.."
if [[ "$(uname -s)" != Darwin ]]; then echo '仅支持 macOS 编译'; exit 1; fi
if ! xcrun --find clang >/dev/null 2>&1; then
    echo '请先运行 xcode-select --install 安装 Apple 命令行工具，再重新运行安装脚本。'; exit 1
fi
export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"
mkdir -p runtime/macos
CRATELOG_OUTPUT="$(mktemp runtime/macos/libcratelog.XXXXXX)"
trap 'rm -f "$CRATELOG_OUTPUT"' EXIT
read -r -a CRATELOG_FLAGS <<< "$(pkg-config --cflags --libs mpv)"
CRATELOG_SOURCE_HASH="$(shasum -a 256 native/cratelog_macos.m | cut -d ' ' -f 1)"
echo "编译目录：$(pwd)"
echo "原生源码 SHA256：$CRATELOG_SOURCE_HASH"
xcrun clang -dynamiclib -fobjc-arc -fblocks -std=gnu11 -O2 \
    "-DCRATELOG_SOURCE_SHA256=\"$CRATELOG_SOURCE_HASH\"" \
    -Wno-deprecated-declarations native/cratelog_macos.m \
    "${CRATELOG_FLAGS[@]}" -framework Cocoa -framework OpenGL \
    -o "$CRATELOG_OUTPUT"
mv "$CRATELOG_OUTPUT" runtime/macos/libcratelog.dylib
echo '已编译 Tk / Cocoa / libmpv Render API 组件。'
echo "输出：$(pwd)/runtime/macos/libcratelog.dylib"

CRATELOG_GESTURE_OUTPUT="$(mktemp runtime/macos/libcratelog_gestures.XXXXXX)"
trap 'rm -f "$CRATELOG_GESTURE_OUTPUT"' EXIT
CRATELOG_GESTURE_HASH="$(shasum -a 256 native/cratelog_gestures.m | cut -d ' ' -f 1)"
xcrun clang -dynamiclib -fobjc-arc -fblocks -O2 \
    "-DCRATELOG_GESTURE_HASH=\"$CRATELOG_GESTURE_HASH\"" \
    native/cratelog_gestures.m -framework Cocoa -o "$CRATELOG_GESTURE_OUTPUT"
mv "$CRATELOG_GESTURE_OUTPUT" runtime/macos/libcratelog_gestures.dylib
echo '已编译原生图片捏合手势组件。'

CRATELOG_TURNTABLE_OUTPUT="$(mktemp runtime/macos/libcratelog_turntable.XXXXXX)"
trap 'rm -f "$CRATELOG_TURNTABLE_OUTPUT"' EXIT
CRATELOG_TURNTABLE_HASH="$(shasum -a 256 native/cratelog_turntable.m | cut -d ' ' -f 1)"
xcrun clang -dynamiclib -fobjc-arc -fblocks -std=gnu11 -O2 \
    "-DCRATELOG_TURNTABLE_HASH=\"$CRATELOG_TURNTABLE_HASH\"" \
    -Wno-deprecated-declarations native/cratelog_turntable.m \
    -framework Cocoa -framework OpenGL -framework CoreText -o "$CRATELOG_TURNTABLE_OUTPUT"
mv "$CRATELOG_TURNTABLE_OUTPUT" runtime/macos/libcratelog_turntable.dylib
echo '已编译唱机 GPU 直接显示组件。'
