"""lambchat_sandbox：LambChat 本地沙箱 daemon 客户端包。

``__version__`` 是客户端与服务端的版本互通地基：daemon connect 的 URL 随
``?version=`` 上报（服务端访问日志可见），channel 注册时存入注册表 hash
value（``node_id|version``），经 ``GET /api/sandbox/status`` 的
``daemon_version`` 字段暴露——为 M3 Tauri 壳随版本更新 / M4 独立 CLI
self-update 与服务端最低版本拒连打底。

自 2.8.6 起 daemon 版本与应用版本保持一致（随发版统一递增，不再走独立的
0.x 序列）；服务端最低版本门（SANDBOX_MIN_DAEMON_VERSION=0.3.1）对
2.x/0.3.x 均放行，旧 daemon 经 self-update 平滑升到对齐版本。
"""

__version__ = "2.10.3"
