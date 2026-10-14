import importlib.util
import struct
import zlib
from pathlib import Path

import pytest


def load_e2e():
    path = Path(__file__).parents[2] / "scripts/e2e_workspace_preview.py"
    spec = importlib.util.spec_from_file_location("workspace_preview_e2e", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_e2e_fixtures_are_valid_large_png_and_zip():
    import base64

    e2e = load_e2e()
    fixtures = e2e.preview_fixtures()
    png = fixtures["images/图片.PNG"]
    assert len(png) > 3 * 1024 * 1024
    assert png[:8] == b"\x89PNG\r\n\x1a\n"
    offset = 8
    image_data = b""
    while offset < len(png):
        size = struct.unpack(">I", png[offset : offset + 4])[0]
        kind = png[offset + 4 : offset + 8]
        data = png[offset + 8 : offset + 8 + size]
        crc = struct.unpack(">I", png[offset + 8 + size : offset + 12 + size])[0]
        assert crc == zlib.crc32(kind + data)
        if kind == b"IDAT":
            image_data += data
        offset += size + 12
    assert len(zlib.decompress(image_data)) == 1025 * 3073
    for name, data in fixtures.items():
        e2e.verify_preview(
            {"encoding": "base64", "content": base64.b64encode(data).decode()},
            data,
            archive=name.endswith(".zip"),
        )
    with pytest.raises(AssertionError, match="corrupt bytes"):
        e2e.verify_preview({"encoding": "base64", "content": "AP8="}, png)


async def test_e2e_stream_checks_detect_truncation():
    e2e = load_e2e()

    async def chunks():
        yield b"abc"
        yield b"def"

    await e2e.verify_stream(chunks(), b"abcdef")
    with pytest.raises(AssertionError, match="truncated stream"):
        await e2e.verify_stream(chunks(), b"abcdefg")
