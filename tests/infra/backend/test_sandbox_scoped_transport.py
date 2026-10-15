from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from deepagents.backends import CompositeBackend

from src.infra.backend.cubesandbox import CubeSandboxBackend
from src.infra.backend.e2b import E2BBackend
from src.infra.sandbox import session_manager as module


def scoped_pair(monkeypatch, platform="e2b", user="owner", sandbox="sandbox-one"):
    monkeypatch.setattr(module.settings, "SANDBOX_PLATFORM", platform)
    manager = module.SessionSandboxManager()
    provider = SimpleNamespace(sandbox_id=sandbox)
    backend_type = CubeSandboxBackend if platform == "cubesandbox" else E2BBackend
    base = backend_type(provider)
    monkeypatch.setattr(module, "create_skills_backend", lambda **kwargs: base)
    manager._cache[user] = (sandbox, CompositeBackend(default=base, routes={}), provider)
    scope = manager._scope_cube_backend if platform == "cubesandbox" else manager._scope_e2b_backend
    first = scope(provider, user, "/home/user/sessions/first").default
    second = scope(provider, user, "/home/user/sessions/second").default
    return manager, provider, first, second


@pytest.mark.parametrize("platform", ["e2b", "cubesandbox"])
async def test_scopes_share_only_sdk_connection_and_keep_paths_and_environments(
    monkeypatch, platform
):
    commands = []

    async def command(**kwargs):
        commands.append(kwargs)
        return SimpleNamespace(stdout="ok", stderr="", exit_code=0)

    client = SimpleNamespace(commands=SimpleNamespace(run=command), set_timeout=AsyncMock())
    connect = AsyncMock(return_value=client)
    monkeypatch.setattr("e2b.AsyncSandbox.connect", connect)
    _manager, _provider, first, second = scoped_pair(monkeypatch, platform)
    first.env_vars = {"RUN": "first"}
    second.env_vars = {"RUN": "second"}
    await first.aexecute("pwd")
    await second.aexecute("pwd")
    assert connect.await_count == 1
    assert "/sessions/first" in commands[0]["cmd"]
    assert "/sessions/second" in commands[1]["cmd"]
    assert commands[0]["envs"] == {"RUN": "first"}
    assert commands[1]["envs"] == {"RUN": "second"}
    assert first is not second


async def test_concurrent_scopes_initialize_sdk_once(monkeypatch):
    entered = asyncio.Event()
    release = asyncio.Event()
    calls = 0
    client = object()

    async def connect(*args, **kwargs):
        nonlocal calls
        calls += 1
        entered.set()
        await release.wait()
        return client

    monkeypatch.setattr("e2b.AsyncSandbox.connect", connect)
    _manager, _provider, first, second = scoped_pair(monkeypatch)
    one = asyncio.create_task(first._async_client_or_none())
    two = asyncio.create_task(second._async_client_or_none())
    await entered.wait()
    release.set()
    assert await one is client
    assert await two is client
    assert calls == 1


async def test_known_cube_handshake_failure_is_not_retried_by_each_scope(monkeypatch):
    connect = AsyncMock(side_effect=json.JSONDecodeError("Expecting value", "", 0))
    monkeypatch.setattr("e2b.AsyncSandbox.connect", connect)
    _manager, _provider, first, second = scoped_pair(monkeypatch, "cubesandbox")
    assert await first._async_client_or_none() is None
    assert await second._async_client_or_none() is None
    assert connect.await_count == 1


async def test_reconnected_sdk_is_visible_to_other_scopes(monkeypatch):
    old_client, new_client = object(), object()
    connect = AsyncMock(side_effect=[old_client, new_client])
    monkeypatch.setattr("e2b.AsyncSandbox.connect", connect)
    _manager, _provider, first, second = scoped_pair(monkeypatch)
    assert await first._async_client_or_none() is old_client
    await second._awake_sandbox_async()
    assert await first._async_client_or_none() is new_client
    assert await second._async_client_or_none() is new_client
    assert connect.await_count == 2


async def test_different_provider_or_owner_cannot_borrow_cached_connection(monkeypatch):
    connect = AsyncMock(side_effect=[object(), object(), object()])
    monkeypatch.setattr("e2b.AsyncSandbox.connect", connect)
    manager, provider, first, _second = scoped_pair(monkeypatch)
    other_owner = manager._scope_e2b_backend(
        provider, "another-owner", "/home/user/sessions/other"
    ).default
    replacement = SimpleNamespace(sandbox_id="sandbox-new")
    other_provider = manager._scope_e2b_backend(
        replacement, "owner", "/home/user/sessions/other"
    ).default
    clients = [await item._async_client_or_none() for item in [first, other_owner, other_provider]]
    assert len({id(client) for client in clients}) == 3
    assert connect.await_count == 3


async def test_work_directory_batch_is_quoted_cached_and_failed_batch_retries(monkeypatch):
    manager = module.SessionSandboxManager()
    execute = AsyncMock(
        side_effect=[
            SimpleNamespace(exit_code=1, output="denied"),
            SimpleNamespace(exit_code=0),
            SimpleNamespace(exit_code=0),
        ]
    )
    backend = SimpleNamespace(default=SimpleNamespace(id="sandbox", aexecute=execute))
    work_dir = "/home/user/sessions/a b"
    with pytest.raises(RuntimeError, match="denied"):
        await manager._ensure_work_dir(backend, work_dir)
    await manager._ensure_work_dir(backend, work_dir)
    await manager._ensure_work_dir(backend, work_dir)
    assert execute.await_count == 2
    assert execute.call_args.args == ("mkdir -p '/home/user/sessions/a b' /home/user/shared",)
