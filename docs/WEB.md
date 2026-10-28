# Optional PHP service / 可选服务端

The desktop app works without this service. Deploy `web/` to a PHP 8.2+ server with PDO SQLite,
mbstring, fileinfo and ZIP support (or configure the existing MySQL backend). Serve over HTTPS.
Copy `cratelog_config.example.php` to `cratelog_config.php`, set a random API token and configure
`CRATELOG_DATA_DIR` to a private, writable directory outside the document root.
Generate a token with `python -c "import secrets; print(secrets.token_urlsafe(48))"`.
Use the full HTTPS `cratelog_api.php` URL and that token in desktop settings.

Review `cratelog_common.php` environment/config options before deployment. The library browsing pages
are designed for a collection site; do not assume the API token protects every read-only page. Put the
entire service behind web-server authentication if the collection is private. Back up the data directory
before running migration/import scripts. Never expose your local development PHP server publicly.
The web UI currently primarily uses Chinese; desktop language selection does not translate it.

桌面本地播放无需服务器。部署前设置强随机令牌、HTTPS 和站点目录之外的数据路径；私密收藏应在
Web 服务器层增加全站认证。迁移或导入前先备份数据。网页界面目前以中文为主。
