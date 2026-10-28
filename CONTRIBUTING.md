# Contributing / 贡献与接手

Use a branch per change. Keep local credentials and music outside Git. Set `CRATELOG_STATE_DIR`
to a disposable directory for testing; never run integration tests against your production server.

Install runtime dependencies, then run `tools/check_translations.py` and the `test_*.py` unittest suite.
PHP integration scripts in `tests/` are opt-in and require local PHP/SQLite (some require MySQL).
Describe the behavior changed, tests run and target OS in each pull request. UI/rendering changes should
include screenshots and an actual desktop check. Mac native changes require a Mac build and playback test.

Translation contributors edit UTF-8 JSON in `locales/`. Preserve placeholder names and do not translate
filenames/album metadata. Organizer key-based strings remain in `translations.py`. Untranslated phrases
fall back to English. RTL shaping/layout needs native-speaker review; choosing Arabic does not imply
complete mirrored layout support.

Release checklist: run CI; build on each target CPU/OS; test packaged playback/rendering on clean machines;
review `dist/build-environment.txt`; include GPL source and dependency licenses; sign/notarize when applicable;
then manually publish a Git tag and release. GitHub workflows do not publish releases automatically.

提交前运行翻译检查及单元测试；界面、播放和原生代码需实机验证。不要提交个人配置、令牌、数据库和音乐。
所有贡献按 GPL-3.0-only 提供；新增依赖需注明许可证及用途。
