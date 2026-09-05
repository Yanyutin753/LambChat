"""lambchat_sandbox：LambChat 本地沙箱 daemon 客户端包。

``__version__`` 是客户端与服务端的版本互通地基：daemon connect 的 URL 随
``?version=`` 上报（服务端访问日志可见），channel 注册时存入注册表 hash
value（``node_id|version``），经 ``GET /api/sandbox/status`` 的
``daemon_version`` 字段暴露——为 M3 Tauri 壳随版本更新 / M4 独立 CLI
self-update 与服务端最低版本拒连打底。发版时同步递增本值。
"""

__version__ = "0.3.0"
