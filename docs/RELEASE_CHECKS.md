# Release validation / 发布验收

The Windows source installer has been exercised with Python 3.12: verified official mpv archive,
Tk and dependency detection, actual mpv decode/IPC playback check. The packaged Windows GUI and
isolated OpenGL helper have been exercised through `Cratelog.exe --self-test report.json`.
The unit suite contains 50 tests. Locale validation covers catalog syntax, formatting placeholders
and English coverage for literal player translation calls.

macOS scripts have been syntax-checked on Windows. No macOS build, playback acceptance, signing or
notarization is claimed from this environment. Run install/build and native rendering checks on both
Apple Silicon and Intel machines you plan to support. Current GitHub macOS workflow only exercises
the architecture of its selected runner.

A package self-test writes a JSON report and uses a temporary settings directory. It verifies UI resource
loading, writable configuration and the actual renderer child. It does not replace listening tests or
verify every audio format. Check head dragging, room lighting, power-off, CUE playback and subtitles manually.

Windows 安装与打包已实测；Mac 仍须实机验收。分发前请完成第三方许可证与对应源码审查，使用自己的
签名身份，并在干净设备上测试。现有源码仓库未绑定远端、未发布任何 GitHub Release。

Hosted CI skips the audio-device playback check and explicitly skips the OpenGL self-test because
runners may lack a graphics driver/audio device. Local default checks do not skip them. CI success
alone is not evidence of working hardware playback or rendering.
