"""search agent 沙箱运行时提示：本机 daemon 会话必须注入机器绑定段。

生产会话 d1def0b5 实测：多机用户（Windows 工作机 + Ubuntu 本机）的 linux
本地会话中模型不知道「这个会话连的是哪台机器/什么系统」，按记忆猜成
Windows 连试三条命令全 404。绑定段（OS+机器名）必须随运行时提示注入。
"""

from src.agents.search_agent import nodes as search_nodes
from src.infra.backend.local import WorkspaceAliasBackend


async def test_runtime_policy_carries_machine_identity(monkeypatch):
    backend = WorkspaceAliasBackend(user_id="u1", session_id="s1")

    async def fake_identity(user_id, machine_id=None):
        assert user_id == "u1"
        return ("linux", "yangyang-Lenovo-XiaoXinPro")

    monkeypatch.setattr("src.infra.backend.local._lookup_daemon_identity", fake_identity)
    policy = await search_nodes._build_sandbox_runtime_policy(
        backend, "/workspace/s1", user_id="u1"
    )
    assert "Linux" in policy
    assert "yangyang-Lenovo-XiaoXinPro" in policy


async def test_runtime_policy_passes_session_machine_id(monkeypatch):
    """会话级选机（多机 daemon）时按目标机查身份，而不是注册表默认解析。"""
    backend = WorkspaceAliasBackend(user_id="u1", session_id="s1", machine_id="mac1")
    seen: dict = {}

    async def fake_identity(user_id, machine_id=None):
        seen["machine_id"] = machine_id
        return ("darwin", "MacBook")

    monkeypatch.setattr("src.infra.backend.local._lookup_daemon_identity", fake_identity)
    await search_nodes._build_sandbox_runtime_policy(backend, "/workspace/s1", user_id="u1")
    assert seen["machine_id"] == "mac1"


async def test_runtime_policy_skips_machine_section_for_non_alias_backend():
    """非本地 daemon 后端（云端沙箱）不加机器绑定段——prompt 保持现状。"""
    policy = await search_nodes._build_sandbox_runtime_policy(
        object(), "/workspace/s1", user_id="u1"
    )
    assert "Local Machine" not in policy
