"""会话级沙箱平台解析测试（Task 9: agent_options.sandbox 路由）。

- `_resolve_sandbox_platform`：agent_options.sandbox ∈ {local, cloud} 时覆盖全局
  平台，否则回退 default_platform（settings.SANDBOX_PLATFORM）。
- `_create_backend_and_prompt` 的 local 分支返回与云端路径相同的 5 元组形状。
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from deepagents.backends import CompositeBackend

from src.agents.search_agent import nodes as search_nodes
from src.agents.search_agent.context import SearchAgentContext
from src.agents.search_agent.nodes import _resolve_sandbox_platform
from src.infra.backend.lazy_sandbox import LazySandboxBackend
from src.infra.backend.local import LocalSandboxBackend

NODES_SOURCE = (
    Path(__file__).resolve().parents[3] / "src" / "agents" / "search_agent" / "nodes.py"
).read_text(encoding="utf-8")


@pytest.mark.parametrize(
    ("agent_options", "expected"),
    [
        ({"sandbox": "local"}, "local"),
        ({"sandbox": "cloud"}, "cloud"),
        ({"sandbox": "bogus"}, "daytona"),
        ({}, "daytona"),
        (None, "daytona"),
    ],
)
def test_resolve_sandbox_platform(agent_options, expected):
    assert _resolve_sandbox_platform(agent_options, "daytona") == expected


def test_local_branch_wired():
    """nodes.py 的后端选择处必须引用 _resolve_sandbox_platform 并含 local 分支（源码结构断言）。"""
    assert "_resolve_sandbox_platform(" in NODES_SOURCE
    assert "LocalSandboxBackend" in NODES_SOURCE


def _patch_store_and_sandbox(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_store() -> object:
        return object()

    monkeypatch.setattr(search_nodes, "acreate_store", fake_store)
    monkeypatch.setattr(search_nodes.settings, "ENABLE_SANDBOX", True)


@pytest.mark.asyncio
async def test_local_option_routes_to_local_sandbox_backend(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """agent_options.sandbox=local 时返回 LocalSandboxBackend 的 5 元组（形状与云端一致）。"""
    _patch_store_and_sandbox(monkeypatch)

    context = SearchAgentContext(session_id="session-1", user_id="user-1")
    backend, prompt, _store, sandbox, work_dir = await search_nodes._create_backend_and_prompt(
        state={"session_id": "session-1"},
        context=context,
        presenter=SimpleNamespace(),
        assistant_id="assistant-user-1",
        agent_options={"sandbox": "local"},
    )

    assert isinstance(backend, CompositeBackend)
    assert isinstance(sandbox, LocalSandboxBackend)
    assert prompt == search_nodes.SANDBOX_SYSTEM_PROMPT
    # daemon 侧 cwd 契约（spec §3.3）：/workspace/{session_id}
    assert work_dir == "/workspace/session-1"
    # 本地后端无云端资源需要释放，不注册 run_sandbox（context.close 不触碰它）
    assert context.run_sandbox is None
    # agent_node 会读取 sandbox_backend.before_tool_start（事件处理器 wiring 契约）
    await sandbox.before_tool_start("execute", {})


@pytest.mark.asyncio
async def test_cloud_platform_still_uses_lazy_backend_without_local_option(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """无 agent_options.sandbox=local 时云端路径保持原样（LazySandboxBackend）。"""
    _patch_store_and_sandbox(monkeypatch)

    context = SearchAgentContext(session_id="session-1", user_id="user-1")
    backend, _prompt, _store, sandbox, _work_dir = await search_nodes._create_backend_and_prompt(
        state={"session_id": "session-1"},
        context=context,
        presenter=SimpleNamespace(),
        assistant_id="assistant-user-1",
    )

    assert isinstance(backend, CompositeBackend)
    assert isinstance(sandbox, LazySandboxBackend)
    assert context.run_sandbox is sandbox
