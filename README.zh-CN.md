# Cratelog

[English](README.md) · [安装与排错](INSTALL.md) · [参与开发](CONTRIBUTING.md)

面向 Windows 与 macOS 的本地音乐资料库、Discogs 专辑整理工具和播放器。
使用 Python/Tk、mpv 与 OpenGL。附带可选 PHP 服务端；不部署服务端也能本地播放。

## 功能

- 浏览专辑目录、封面、音频标签、多碟专辑和 CUE 分轨。
- 本地播放、频谱、字幕、循环模式、专辑评价。
- 交互唱机：空白处拖动调整视角，滚轮缩放；提起唱头，左拖选后面的曲目，右拖选前面的曲目，松手播放。
- 左上曲目菜单，旁边灯泡切换环境照明；右下悬停显示视角盘。关闭唱机电源会停止播放并熄灭全部 LED。
- Discogs 搜索、文件夹整理、Excel 导出。
- 可选 Last.fm 聆听记录、自建服务端同步与冲突处理。
- 12 种可选语言，未翻译的次级对话框回退英文，详见 [语言覆盖说明](LANGUAGES.md)。

## 一键安装、运行与编译

先下载或克隆代码到可写目录；本地播放无需注册账号或提供 API 密钥。

| 系统 | 安装 | 运行 | 编译打包 |
| --- | --- | --- | --- |
| Windows 10/11 64 位 | 双击 `install_windows.bat` | `start_windows.bat` | `build_windows.bat` |
| macOS Apple Silicon / Intel | `bash install_macos.command` | `start_macos.command` 或生成的 `Cratelog.app` | `bash build_macos.command` |

Windows：缺少 Python 3.12 时通过 winget 安装，自动建立虚拟环境，下载并校验官方 mpv 的 SHA256。
缺少 winget 时先从微软商店安装“应用安装程序”。

macOS：需要先安装 [Homebrew](https://brew.sh) 和 Apple Command Line Tools；脚本会检查并提示，
之后安装 Python/Tk、mpv、FFmpeg，编译 Cocoa 原生组件。运行 `chmod +x *.command` 后可在 Finder 双击。
安装需要联网，可重复执行，不会删除音乐或用户设置。

请在目标系统及 CPU 架构上编译。Windows 输出 `dist/Cratelog/Cratelog.exe`，必须保留整个目录；
macOS 输出 `dist/Cratelog.app`。项目根目录生成的 Mac app 只是依赖源码目录的启动器，`dist` 中才是打包结果。
产物尚未代码签名；Mac 公共分发需要维护者自己的签名和公证身份。详见 [INSTALL.md](INSTALL.md)。

## 首次使用与隐私

选择音乐根目录、专辑和曲目即可播放。需要整理专辑时，在整理器内填写自己的 Discogs Token。
服务端同步和 Last.fm 都是可选功能，需自行配置地址或授权。仓库不含个人凭据、数据库或音乐文件。

设置与待提交聆听记录保存到 Windows 的 `%APPDATA%/Cratelog` 或 macOS 的
`~/Library/Application Support/Cratelog`。可用 `CRATELOG_STATE_DIR` 指定测试目录。
删除源码目录不会删除用户设置；如需从旧版本迁移，可自行将旧设置文件复制到新目录。

## 开发与接手

建立 Python 虚拟环境后安装 `requirements.txt`，运行 `python cratelog.py`。

```sh
python tools/check_translations.py
python -m unittest discover -s tests -p 'test_*.py'
```

部分测试需要桌面/Tk 环境。测试时请设置 `CRATELOG_STATE_DIR` 为临时目录。
播放器入口在 `cratelog_player.py`，整理器在 `cratelog.py`，唱机在 `cratelog_turntable.py/.frag`，
原生 Mac 组件在 `native/`，安装构建工具在 `tools/`，语言包在 `locales/`，可选服务端在 `web/`。
阅读 [贡献指南](CONTRIBUTING.md) 与 [服务端部署](docs/WEB.md)。

CI 提供跨平台单元测试；手动触发打包工作流后下载构建附件，不会自动发布 Release。

## 许可证

Copyright 2026 HITLIKE。项目代码采用 [GPL-3.0-only](LICENSE)。
依赖许可与分发说明见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。
发布二进制时需提供对应源码和依赖许可；音乐、封面、Discogs 数据不因本项目而获得新的授权。
本项目与 Technics、Discogs 无隶属关系。
