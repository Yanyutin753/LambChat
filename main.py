def run() -> None:
    """Start the application server."""
    import os

    import uvicorn

    from src.kernel.config import settings

    # 优雅停机窗口：SSE agent 流可持续数分钟，30s 会把滚动更新变成
    # 硬断流（靠前端对账自愈）。120s 让多数 run 自然收尾，超长的由
    # checkpoint 恢复机制接管。k8s terminationGracePeriodSeconds 须大于此值。
    graceful_timeout = int(os.getenv("GRACEFUL_SHUTDOWN_TIMEOUT", "120"))

    uvicorn.run(
        "src.api.main:app",
        host="0.0.0.0",
        port=settings.PORT,
        reload=settings.DEBUG and os.getenv("UVICORN_RELOAD", "true").lower() == "true",
        log_level="info",
        timeout_graceful_shutdown=graceful_timeout,
        # 即使 reload=True 在生产环境也不影响，DEBUG 控制
    )


if __name__ == "__main__":
    run()
