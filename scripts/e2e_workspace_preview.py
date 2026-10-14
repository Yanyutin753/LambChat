"""Real cloud workspace API E2E, against a local server using its configured sandbox.

Run under scripts/run_validation.py. Set E2E_WORKSPACE_TOKEN to the session owner's
JWT, then pass --session-id. Only a unique test directory is created and removed.
No model calls, production URLs, platform changes, or new sandbox creation.
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import hashlib
import io
import json
import os
import random
import shlex
import struct
import sys
import tempfile
import time
import uuid
import zipfile
import zlib
from pathlib import Path
from urllib.parse import urlsplit

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def preview_fixtures(image_mib: int = 3) -> dict[str, bytes]:
    """A valid incompressible PNG and a ZIP, both above the model read limit."""
    width = 1024
    height = (image_mib * 1024 * 1024) // (width * 3) + 1
    rng = random.Random(42)
    pixels = b"".join(b"\x00" + rng.randbytes(width * 3) for _ in range(height))

    def chunk(kind: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))
        )

    image = (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(pixels, level=0))
        + chunk(b"IEND", b"")
    )
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_STORED) as zipped:
        zipped.writestr("images/图片.PNG", image)
        zipped.writestr("images/copy.png", image)
    return {"images/图片.PNG": image, "images.zip": archive.getvalue(), "empty.bin": b""}


def verify_preview(body: dict, expected: bytes, *, archive: bool = False) -> None:
    assert not body.get("error"), body.get("error")
    assert body.get("encoding") == "base64", body.get("encoding")
    actual = base64.b64decode(body["content"], validate=True)
    assert hashlib.sha256(actual).digest() == hashlib.sha256(expected).digest(), "corrupt bytes"
    if archive:
        with zipfile.ZipFile(io.BytesIO(actual)) as zipped:
            assert zipped.testzip() is None, "corrupt ZIP entry"
            assert zipped.namelist() == ["images/图片.PNG", "images/copy.png"]


async def verify_stream(chunks, expected: bytes, *, archive: bool = False) -> None:
    digest = hashlib.sha256()
    total = 0
    with tempfile.TemporaryFile() as output:
        async for chunk in chunks:
            digest.update(chunk)
            total += len(chunk)
            output.write(chunk)
        assert total == len(expected), "truncated stream"
        assert digest.digest() == hashlib.sha256(expected).digest(), "corrupt stream"
        if archive:
            output.seek(0)
            with zipfile.ZipFile(output) as zipped:
                assert zipped.testzip() is None
                assert zipped.namelist() == ["images/图片.PNG", "images/copy.png"]


async def run(args) -> None:
    from src.infra.sandbox.session_manager import get_session_sandbox_manager
    from src.kernel.config import settings
    from src.kernel.config.service import initialize_settings

    await initialize_settings()
    assert settings.SANDBOX_PLATFORM in {"cubesandbox", "e2b", "daytona"}, "cloud platform required"
    token = os.environ["E2E_WORKSPACE_TOKEN"]
    headers = {"Authorization": f"Bearer {token}"}
    async with httpx.AsyncClient(base_url=args.server, headers=headers, timeout=60) as client:
        me = await client.get("/api/auth/me")
        me.raise_for_status()
        user_id = me.json()["id"]
        # Validate ownership through the actual route before creating any fixtures.
        root = await client.get(
            "/api/sandbox/fs/cloud/list", params={"session_id": args.session_id}
        )
        root.raise_for_status()
        assert not root.json().get("error"), root.json().get("error")
        backend, _ = await get_session_sandbox_manager().get_or_create(
            args.session_id, user_id, create=False
        )
        directory = f"workspace-preview-e2e-{uuid.uuid4().hex}"
        fixtures = preview_fixtures(args.image_mib)
        try:
            uploads = await backend.aupload_files(
                [(f"{directory}/{name}", content) for name, content in fixtures.items()]
            )
            assert len(uploads) == len(fixtures) and all(not item.error for item in uploads), (
                "upload failed"
            )
            for name, expected in fixtures.items():
                started = time.monotonic()
                async with client.stream(
                    "GET",
                    "/api/sandbox/fs/cloud/read",
                    params={
                        "session_id": args.session_id,
                        "path": f"./{directory}/{name}",
                        "stream": "true",
                    },
                ) as response:
                    response.raise_for_status()
                    assert response.headers["content-type"] == "application/octet-stream"
                    await verify_stream(
                        response.aiter_bytes(), expected, archive=name.endswith(".zip")
                    )
                elapsed = time.monotonic() - started
                print(
                    json.dumps({"file": name, "bytes": len(expected), "seconds": round(elapsed, 3)})
                )
            missing = await client.get(
                "/api/sandbox/fs/cloud/read",
                params={
                    "session_id": args.session_id,
                    "path": f"{directory}/missing.png",
                    "stream": "true",
                },
            )
            missing.raise_for_status()
            assert missing.json().get("error"), "missing file must return an error"
            print("PASS: real cloud PNG/ZIP/empty/missing workspace previews")
        finally:
            result = await backend.aexecute(f"rm -rf -- {shlex.quote(directory)}")
            assert result.exit_code == 0, "E2E fixture cleanup failed"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--server", default="http://127.0.0.1:8000")
    parser.add_argument("--session-id", required=True)
    parser.add_argument("--image-mib", type=int, default=3)
    args = parser.parse_args()
    parsed = urlsplit(args.server)
    if parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
        parser.error("use a local backend with the same settings/database as this checkout")
    if not 3 <= args.image_mib <= 24:
        parser.error("--image-mib must be 3..24; the ZIP contains two images")
    asyncio.run(run(args))


if __name__ == "__main__":
    from run_validation import validation_slot

    with validation_slot():
        main()
