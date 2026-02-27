if __name__ == "__main__":
    import uvicorn

    from src.kernel.config import settings

    uvicorn.run(
        "src.api.main:app",
        host="0.0.0.0",
        port=settings.PORT,
        reload=settings.DEBUG,
        log_level="info",
    )
