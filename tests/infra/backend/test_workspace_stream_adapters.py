from types import SimpleNamespace


async def test_daytona_awaits_stream_factory_and_closes_source(monkeypatch):
    import daytona

    from src.infra.backend.daytona import DaytonaBackend

    closed = []

    async def chunks():
        try:
            yield b"abc"
            yield b"def"
        finally:
            closed.append("stream")

    async def download(path, timeout):
        assert path == "/w/image.png"
        return chunks()

    class Client:
        def __init__(self, *_args):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            closed.append("client")

        async def get(self, _id):
            return SimpleNamespace(fs=SimpleNamespace(download_file_stream=download))

    monkeypatch.setattr(daytona, "AsyncDaytona", Client)
    backend = DaytonaBackend(SimpleNamespace(id="sandbox"), work_dir="/w")
    monkeypatch.setattr(backend, "_file_size", lambda path: 6)
    stream = backend.astream_file("image.png")
    assert await anext(stream) == b"abc"
    await stream.aclose()
    assert closed == ["stream", "client"]


async def test_e2b_async_stream_is_closed_on_cancel(monkeypatch):
    from src.infra.backend.e2b import E2BBackend

    closed = []

    class Reader:
        def __aiter__(self):
            return self

        async def __anext__(self):
            return b"abc"

        async def aclose(self):
            closed.append(True)

    async def read(path, format):
        assert (path, format) == ("/w/image.png", "stream")
        return Reader()

    async def client():
        return SimpleNamespace(files=SimpleNamespace(read=read))

    async def sdk(_name, call):
        return await call()

    backend = E2BBackend(SimpleNamespace(sandbox_id="sandbox"), work_dir="/w")
    monkeypatch.setattr(backend, "_file_size", lambda path: 6)
    monkeypatch.setattr(backend, "_async_client_or_none", client)
    monkeypatch.setattr(backend, "_asdk", sdk)
    stream = backend.astream_file("image.png")
    assert await anext(stream) == b"abc"
    await stream.aclose()
    assert closed == [True]


async def test_e2b_stream_falls_back_to_sync_lane_when_async_unavailable(monkeypatch):
    from src.infra.backend.e2b import E2BBackend

    payload = b"x" * (300 * 1024)

    async def no_client():
        return None

    def download_files(paths):
        assert paths == ["/w/image.png"]
        return [SimpleNamespace(path="/w/image.png", content=payload, error=None)]

    backend = E2BBackend(SimpleNamespace(sandbox_id="sandbox"), work_dir="/w")
    monkeypatch.setattr(backend, "_file_size", lambda path: len(payload))
    monkeypatch.setattr(backend, "_async_client_or_none", no_client)
    monkeypatch.setattr(backend, "download_files", download_files)
    chunks = [chunk async for chunk in backend.astream_file("image.png")]
    assert b"".join(chunks) == payload
    assert max(len(chunk) for chunk in chunks) <= 256 * 1024
    assert len(chunks) == 2
