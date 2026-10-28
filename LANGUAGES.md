# Languages / 多语言

Selectable: 简体中文、繁體中文、English、Español、Português、Français、Deutsch、日本語、한국어、Русский、العربية、हिन्दी。
The app also supports automatic system-language detection. Changes in Settings apply after restart.
`CRATELOG_LANGUAGE` overrides automatic detection for testing; an explicit saved selection takes precedence.

Player translations are UTF-8 JSON files in `locales/`; organizer strings remain in `translations.py`.
English and simplified Chinese cover the current 291 catalog phrases; other locales currently cover
105–125 phrases and use English for the rest. These figures describe catalog entries, not all arbitrary
status/error strings. Backend diagnostics and the optional PHP frontend are not fully localized.
Arabic RTL mirroring and font shaping need further platform/native-speaker validation.

Run `python tools/check_translations.py` for current coverage, placeholder validation and missing English
translations in literal `tr(...)` calls. Add new UI messages through `tr(...)`; never feed album titles
or user-authored comments through translation replacement. Existing tests protect that distinction.

简体中文和英文目录较完整，其余语言保留现有翻译、缺失部分回退英文，不宣称全部对话框已完成翻译。
欢迎编辑 `locales/<语言>.json` 补齐译文，保留格式占位符，然后运行翻译检查。
