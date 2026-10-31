# Installation and builds / 安装与构建

## Windows

Run `install_windows.bat`, then `start_windows.bat`. Python 3.12 + Tk, Python dependencies,
and pinned official mpv 0.41.0 are installed. The mpv archive checksum is verified before extraction.
No third-party binary is tracked in Git. The installed `runtime/mpv` directory is reused on subsequent runs.
To update mpv, review the upstream release and checksum and update the installer together.

If Python is installed for all users but the launcher is absent, install the Python launcher or
Python 3.12 per-user. App Installer supplies winget. An Internet connection is required.
For manual setup: create `.venv`, install `requirements.txt`, place mpv at `runtime/mpv/mpv.exe`
(with all DLLs), and run `.venv/Scripts/python cratelog.py`. FFmpeg is optional on Windows;
install it separately and add it to PATH if you need external FFmpeg tooling.

`build_windows.bat` installs build dependencies and creates a PyInstaller directory build.
It includes a separate console renderer because the GUI executable has no binary stdin/stdout pipes.
Do not launch the renderer yourself; the GUI manages it. `dist/build-environment.txt` records package versions.

## macOS

Install Homebrew from https://brew.sh and run `xcode-select --install` once. These prerequisites
may prompt for system approval; the installer does not silently run a downloaded bootstrap script.
Then run `bash install_macos.command`. It installs Python 3.14 and matching Tk, mpv, FFmpeg and
pkg-config; creates `.venv-macos`; compiles `native/*.m`; verifies installation and creates a Finder launcher.

Run `bash build_macos.command` to build `dist/Cratelog.app` on the target architecture.
PyInstaller collects the native bridges and their linked libraries. Verify on a clean target Mac;
Homebrew paths, architecture and nested helper signing must be checked before public distribution.
No Apple certificate is included. Sign the nested helper executables/libraries before signing the outer app,
and notarize using your own Apple developer credentials. Do not disable Gatekeeper globally.
The builder includes mpv and the linked native libraries. A local ad-hoc signature is applied after
assembling the helper. This is not Developer ID signing or notarization. Verify the bundle on a Mac
without the build machine's Homebrew paths before advertising a self-contained public release.

## Verification / 验证

```sh
python tools/check_install.py --playback
python tools/check_translations.py
python -m unittest discover -s tests -p 'test_*.py'
```

Mac native UI acceptance: `.venv-macos/bin/python tools/check_macos_render.py` in a desktop session.
Test actual audio, track changes, CUE files, window resizing, turntable lighting/power and head dragging.
OpenGL 3.3 and a working graphics driver are required for the turntable; basic playback can still be used
when the renderer fails. Windows playback is based on an external mpv process; macOS uses the native libmpv bridge.

## Troubleshooting / 排错

- Missing Tk: reinstall Python with Tcl/Tk on Windows; on Mac use matching `python-tk@3.14`.
- Missing mpv: rerun installer, check `runtime/mpv/mpv.exe` on Windows or `brew install mpv` on Mac.
- Native library mismatch: rebuild using `bash tools/build_macos.sh` from the same checkout/architecture.
- Permission denied: keep source in a writable directory; settings are in the per-user app-data directory.
- GUI startup failure: run the virtualenv Python against `cratelog.py` in a terminal for the traceback.
- Downloads fail: retry after checking proxy/firewall settings. Never bypass checksum verification.

## Uninstall / 卸载

Delete the checkout or packaged app. User settings are kept independently; remove the Cratelog app-data
folder only if you want to erase settings, authorization and queued scrobbles. Music folders are never removed
by installation/uninstallation. Python/Homebrew packages are shared system tools and are not uninstalled automatically.


### Mac 唱机 GPU 直接显示

更新源码后，在 Mac 项目目录执行 `bash tools/build_macos.sh`，重新启动播放器。
唱机优先使用 `runtime/macos/libcratelog_turntable.dylib`，保留原有着色器和超采样，
GPU 内缩放后直接显示；不再将每帧画面读回 Python。菜单纹理仅在内容改变时上传。
组件缺失、源码版本不一致或初始化/绘制失败时，自动使用原图片渲染路径，并在状态栏说明。

真实原生组件验证：`.venv-macos/bin/python tools/check_turntable_native.py --seconds 15`。
它会显示日间、夜间唱机，并输出帧率和该进程 CPU；该脚本遇到原生组件问题直接失败，不会悄悄回退。
需另行实机检查 Retina/外接屏、窗口缩放、最小化恢复、菜单、双指手势和刮碟。
若需对比旧路径，使用 `CRATELOG_TURNTABLE_RENDERER=compat .venv-macos/bin/python cratelog.py` 启动。
比较时使用相同曲目、窗口尺寸、显示器和界面，记录主进程、子进程总 CPU 和 GPU 功耗。
Windows 回归通过不代表 Cocoa 编译、Mac 画质或性能已经验证。
