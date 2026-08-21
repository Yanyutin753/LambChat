def run() -> None:
    """Start the application server."""
    import os

    import uvicorn

    from src.kernel.config import settings

    uvicorn.run(
        "src.api.main:app",
        host="0.0.0.0",
        port=settings.PORT,
        reload=settings.DEBUG and os.getenv("UVICORN_RELOAD", "true").lower() == "true",
        log_level="info",
        timeout_graceful_shutdown=30,
        # 即使 reload=True 在生产环境也不影响，DEBUG 控制
    )


if __name__ == "__main__":
    run()
