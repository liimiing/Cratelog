# Third-party components

Project code: Copyright 2026 HITLIKE, GPL-3.0-only. See LICENSE.
Dependencies retain their own licenses; this document is an inventory, not a substitute for their full notices.

| Component | Purpose | Upstream / license family |
| --- | --- | --- |
| Python, Tcl/Tk | Runtime and desktop UI | python.org (PSF); tcl.tk (Tcl/Tk licenses) |
| requests / urllib3 / certifi | HTTP and certificates | requests.readthedocs.io (Apache-2.0); urllib3 (MIT); certifi (MPL-2.0) |
| Pillow | Images | python-pillow.org (HPND) |
| mutagen | Audio tags | mutagen.readthedocs.io (GPL-2.0-or-later) |
| openpyxl | Excel export | openpyxl.readthedocs.io (MIT) |
| pyglet | OpenGL context | pyglet.org (BSD-3-Clause) |
| mpv / libmpv | Playback | mpv.io (GPL/LGPL depending on build configuration) |
| FFmpeg | Multimedia tooling | ffmpeg.org (LGPL/GPL depending on build configuration) |
| PyInstaller | Build tooling | pyinstaller.org (GPL with bootloader exception) |

Windows installer downloads official mpv releases, verifies the pinned checksum and preserves archive contents.
When redistributing a built bundle, retain all dependency notices and satisfy the exact build's corresponding
source obligations, including transitive codec libraries. Review upstream build recipes rather than assuming
all mpv/FFmpeg binaries have identical licensing. macOS Homebrew dependencies remain separately installed.

Album art, audio, metadata, names and third-party service trademarks are not included under the code license.
No reference manuals, personal collection spreadsheets, account tokens or database dumps are shipped.
