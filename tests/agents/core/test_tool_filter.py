from __future__ import annotations

import asyncio

import pytest

from src.agents.core.tool_filter import get_db_disabled_mcp_tool_names


@pytest.mark.asyncio
async def test_db_disabled_mcp_queries_start_together(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    release = asyncio.Event()
    started: set[str] = set()

    class _FakeStorage:
        async def _gated(self, name: str, value):
            started.add(name)
            await release.wait()
            return value

        async def get_system_disabled_tools(self):
            return await self._gated("system", {"system-server": ["blocked-system-tool"]})

        async def get_user_server_disabled_tools(self, user_id: str):
            assert user_id == "user-1"
            return await self._gated("server", {"user-server": ["blocked-user-tool"]})

        async def get_disabled_tool_names(self, user_id: str):
            assert user_id == "user-1"
            return await self._gated(
                "preference",
                {"preference-server:blocked-preference-tool"},
            )

    monkeypatch.setattr("src.infra.mcp.storage.MCPStorage", _FakeStorage)

    task = asyncio.create_task(get_db_disabled_mcp_tool_names("user-1"))
    for _ in range(20):
        if len(started) == 3:
            break
        await asyncio.sleep(0)

    assert started == {"system", "server", "preference"}
    release.set()
    assert await task == {
        "system-server:blocked-system-tool",
        "user-server:blocked-user-tool",
        "preference-server:blocked-preference-tool",
    }
