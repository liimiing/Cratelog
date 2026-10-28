# Cratelog

[简体中文](README.zh-CN.md) · [Installation](INSTALL.md) · [Contributing](CONTRIBUTING.md)

A desktop music library, Discogs organizer and local player for Windows and macOS.
Built with Python/Tk, mpv and an OpenGL turntable renderer. An optional PHP service hosts
album metadata, artwork and documents; local playback works without a server.

## Features

- Browse album folders, covers, tags, multi-disc albums and CUE tracks.
- Play local audio with spectrum visualization, subtitles and playback modes.
- Interactive turntable: drag to orbit, scroll to zoom, lift the headshell and drag
  left for later tracks / right for earlier tracks; release to play.
- Hover the upper-left list icon for tracks; the adjacent bulb toggles room lighting.
  Hover the lower-right corner for camera controls. Turning off deck power stops playback
  and extinguishes every deck LED.
- Search Discogs, organize folders and export album metadata to Excel.
- Optional Last.fm scrobbling and self-hosted synchronization with conflict handling.
- Twelve selectable languages; English fallback for untranslated secondary dialogs.
  See [translation coverage](LANGUAGES.md).

## Quick start

Download/clone the source to a writable folder. No API key or account is required for local playback.

| System | Install | Start | Build |
| --- | --- | --- | --- |
| Windows 10/11, 64-bit | Double-click `install_windows.bat` | `start_windows.bat` | `build_windows.bat` |
| macOS, Apple Silicon / Intel | `bash install_macos.command` | `start_macos.command` or generated `Cratelog.app` | `bash build_macos.command` |

Windows bootstrap requires App Installer/winget if Python 3.12 is absent. It installs Python,
creates an isolated virtualenv and verifies the SHA256 of a pinned official mpv download.
macOS requires [Homebrew](https://brew.sh) and Apple Command Line Tools; the script explains
how to install missing prerequisites, then installs Python/Tk, mpv and FFmpeg and compiles
native Cocoa components. Finder can open `.command` files after `chmod +x *.command`.
Installers need Internet access and can be rerun. They do not delete your music or settings.

Build on the target OS/CPU. Windows output: `dist/Cratelog/Cratelog.exe`; macOS output:
`dist/Cratelog.app`. Copy the entire output folder/app, not just the executable.
The source-install Mac app is a launcher tied to the checkout; the app under `dist` is the
packaged build. Packages are unsigned; macOS signing/notarization requires your own Apple identity.
Read [INSTALL.md](INSTALL.md) for dependencies, verification and troubleshooting.

## First run and privacy

Choose a music folder, then an album and track. Add your own Discogs token in the organizer
only if you need metadata lookup. Configure your own server URL/token and Last.fm credentials
only when enabling those features. No credentials or personal library are included.
Settings and queued scrobbles are stored in `%APPDATA%/Cratelog` on Windows or
`~/Library/Application Support/Cratelog` on macOS. `CRATELOG_STATE_DIR` overrides this location
for tests/portable development. Deleting the checkout does not delete those settings.

## Development

```sh
python -m venv .venv
# Activate .venv using your shell, then:
python -m pip install -r requirements.txt
python tools/check_translations.py
python -m unittest discover -s tests -p 'test_*.py'
python cratelog.py
```

Tk must be available. Some tests create windows and require a desktop session.
Use `CRATELOG_STATE_DIR` pointing to a temporary folder during tests. The installers provide
mpv separately. macOS native code builds with `bash tools/build_macos.sh`.

- `cratelog_player.py`: player and library UI; `cratelog.py`: Discogs organizer.
- `cratelog_turntable.py` / `.frag`: interactions and isolated OpenGL rendering.
- `native/`: Cocoa/libmpv bridge and gestures; `tools/`: installers, builders and checks.
- `locales/`, `translations.py`: player catalogs and organizer strings.
- `web/`: optional PHP service; see [web deployment](docs/WEB.md).

CI validates catalogs and runs a cross-platform unit-test matrix. Builds are manually dispatched
and uploaded as workflow artifacts; they are not published as releases automatically.

## License

Copyright 2026 HITLIKE. Project code is licensed under [GPL-3.0-only](LICENSE).
See [third-party notices](THIRD_PARTY_NOTICES.md). Before distributing binaries, include the
corresponding source and required dependency notices. Artwork/music/Discogs data are not
relicensed by this project. This is an independent project, not a Technics or Discogs product.
