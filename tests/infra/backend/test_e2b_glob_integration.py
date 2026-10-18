from __future__ import annotations

import os

import pytest
from pymongo import AsyncMongoClient

from src.infra.settings.service import SettingsService
from src.infra.storage.mongodb import build_mongo_connection_string
from src.kernel.config import settings


@pytest.mark.asyncio
async def test_e2b_glob_finds_nested_and_root_hello_py_in_real_sandbox() -> None:
    if os.environ.get("RUN_SANDBOX_INTEGRATION") != "1":
        pytest.skip("set RUN_SANDBOX_INTEGRATION=1 to run real sandbox integration tests")

    service = SettingsService()
    async with AsyncMongoClient(build_mongo_connection_string()) as client:
        service._storage._collection = client[settings.MONGODB_DB]["system_settings"]
        api_key_item = await service._storage.get_raw("E2B_API_KEY")
        template_item = await service._storage.get_raw("E2B_TEMPLATE")
        timeout_item = await service._storage.get_raw("E2B_TIMEOUT")

    if api_key_item is None or api_key_item.updated_at is None:
        pytest.skip("E2B_API_KEY is not configured in database settings")

    from src.infra.sandbox.base import SandboxFactory

    backend = SandboxFactory.create_e2b(
        api_key=api_key_item.value,
        template=template_item.value if template_item is not None else "base",
        timeout=int(timeout_item.value) if timeout_item is not None else 120,
        auto_pause=False,
    )
    try:
        backend.execute("mkdir -p /home/user/project/lib")
        backend.write("/home/user/hello.py", "print('root')\n")
        backend.write("/home/user/project/hello.py", "print('nested')\n")
        backend.write("/home/user/project/lib/hello.py", "print('deep')\n")
        backend.execute(
            "mkdir -p /home/user/src/tests /home/user/src/pkg/deep/tests "
            "/home/user/src/pkg/not-tests"
        )
        backend.write("/home/user/src/tests/root.py", "print('root test')\n")
        backend.write("/home/user/src/pkg/deep/tests/deep.py", "print('deep test')\n")
        backend.write("/home/user/src/pkg/not-tests/deep.py", "print('nope')\n")

        result = backend.glob("**/hello.py", path="/")

        assert result.error is None
        paths = {match["path"] for match in result.matches}
        assert {
            "/home/user/hello.py",
            "/home/user/project/hello.py",
            "/home/user/project/lib/hello.py",
        }.issubset(paths)

        nested_result = backend.glob("src/**/tests/*.py", path="/")
        assert nested_result.error is None
        nested_paths = {match["path"] for match in nested_result.matches}
        assert {
            "/home/user/src/tests/root.py",
            "/home/user/src/pkg/deep/tests/deep.py",
        }.issubset(nested_paths)
        assert "/home/user/src/pkg/not-tests/deep.py" not in nested_paths
    finally:
        close = getattr(backend._sandbox, "kill", None)
        if close is not None:
            close()
