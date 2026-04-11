"""
延迟工具管理器 — 管理按需加载的 MCP 工具生命周期。

启动时只保留轻量的工具名列表（通过系统提示告知 LLM），
当 LLM 通过 search_tools 搜索时，将匹配的工具提升为"已发现"状态。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Optional

from src.infra.logging import get_logger

if TYPE_CHECKING:
    from langchain_core.tools import BaseTool

logger = get_logger(__name__)


def _tool_sort_key(tool: "BaseTool") -> tuple[str, str]:
    return (getattr(tool, "server", "") or "", getattr(tool, "name", "") or "")


@dataclass
class DeferredToolStub:
    """延迟工具的轻量描述（用于系统提示注入）"""

    name: str
    description: str  # 首行，截断
    server: str = ""
    is_mcp: bool = False


class DeferredToolManager:
    """管理延迟 MCP 工具的发现和提升

    内置 dirty flag 机制：stubs 和 prompt string 仅在 discover_tools() 后才重建，
    避免每次 LLM 调用时重复分配。
    """

    def __init__(
        self,
        all_deferred_tools: list["BaseTool"],
        session_id: str,
        disabled_tools: Optional[list[str]] = None,
        pre_discovered_names: Optional[list[str]] = None,
    ):
        # 应用 disabled_tools 过滤
        disabled_set = set(disabled_tools or [])
        mcp_servers = {t[4:] for t in disabled_set if t.startswith("mcp:")}
        exact_disabled = disabled_set - {f"mcp:{s}" for s in mcp_servers}

        filtered: list["BaseTool"] = []
        for tool in all_deferred_tools:
            name = getattr(tool, "name", "")
            if name in exact_disabled:
                continue
            # mcp:server 前缀过滤
            server = getattr(tool, "server", "")
            if server in mcp_servers:
                continue
            # 名称前缀过滤
            for s in mcp_servers:
                if name.startswith(f"{s}:"):
                    break
            else:
                filtered.append(tool)

        self._all_tools: list["BaseTool"] = sorted(filtered, key=_tool_sort_key)
        self._tool_map: dict[str, "BaseTool"] = {t.name: t for t in filtered}
        # 恢复上次已发现工具（从 store 持久化的数据）
        pre_set = set(pre_discovered_names or []) & set(self._tool_map.keys())
        self._discovered_names: set[str] = pre_set
        self._session_id = session_id

        # Dirty flag: 当 discover_tools() 被调用后设为 True
        # 外部消费者检查此 flag 决定是否需要重建缓存
        self.stale: bool = True

        # 缓存
        self._cached_stubs: list[DeferredToolStub] = []
        self._cached_stubs_string: str = ""

        logger.info(
            "[DeferredToolManager] Created: %d deferred tools for session %s "
            "(%d pre-restored from store)",
            len(filtered),
            session_id,
            len(pre_set),
        )

    @property
    def total_deferred(self) -> int:
        """延迟工具总数"""
        return len(self._all_tools)

    @property
    def discovered_count(self) -> int:
        """已发现工具数"""
        return len(self._discovered_names)

    @property
    def discovered_names(self) -> list[str]:
        """已发现工具名列表"""
        return sorted(self._discovered_names)

    @property
    def remaining_count(self) -> int:
        """剩余未发现工具数"""
        return self.total_deferred - self.discovered_count

    def get_deferred_stubs(self) -> list[DeferredToolStub]:
        """获取未发现工具的轻量描述列表（带脏标记缓存）"""
        if not self.stale:
            return self._cached_stubs

        stubs: list[DeferredToolStub] = []
        for tool in self._all_tools:
            if tool.name in self._discovered_names:
                continue
            desc = getattr(tool, "description", "") or ""
            hint = desc.split("\n")[0].strip()[:120]
            stubs.append(
                DeferredToolStub(
                    name=tool.name,
                    description=hint,
                    server=getattr(tool, "server", ""),
                    is_mcp=True,
                )
            )

        self._cached_stubs = sorted(stubs, key=lambda stub: (stub.server, stub.name))
        self.stale = False
        return self._cached_stubs

    def get_deferred_stubs_string(self) -> str:
        """返回可直接拼入系统提示的预格式化字符串（带脏标记缓存）。

        包含两部分：
        1. 未发现工具列表 — Agent 需通过 search_tools 加载
        2. 已发现工具列表 — Agent 可直接使用（schema 已注入 request.tools）
        """
        if not self.stale:
            return self._cached_stubs_string

        parts: list[str] = []

        # 已发现工具（直接可用）
        if self._discovered_names:
            discovered_lines = "\n".join(f"- {name}" for name in sorted(self._discovered_names))
            parts.append(
                "## MCP Tools (Loaded)\n\n"
                "These tools are loaded and ready to use:\n\n"
                f"{discovered_lines}\n"
            )

        # 未发现工具（需要 search_tools）
        stubs = self.get_deferred_stubs()  # 调用后 stale=False 并更新缓存
        if stubs:
            lines = "\n".join(f"- {s.name}: {s.description}" for s in stubs)
            parts.append(
                "## MCP Tools (Deferred)\n\n"
                "The following tools are available but not yet loaded. "
                "Call `search_tools` to load their full parameter schemas before using them. "
                "`search_tools` only searches the deferred MCP tools listed in this section; "
                "it does NOT search sandbox MCP tools. Use `mcporter` inside the sandbox to "
                "discover those tools.\n\n"
                f"{lines}\n"
            )

        if not parts:
            self._cached_stubs_string = ""
            return ""

        result = "\n\n".join(parts)
        self._cached_stubs_string = result
        return result

    def get_discovered_tools(self) -> list["BaseTool"]:
        """获取已发现工具的完整 BaseTool 列表"""
        return [self._tool_map[n] for n in sorted(self._discovered_names) if n in self._tool_map]

    def get_undiscovered_tools(self) -> list["BaseTool"]:
        """获取未发现工具的完整 BaseTool 列表（用于搜索）"""
        return [t for t in self._all_tools if t.name not in self._discovered_names]

    def discover_tools(self, names: list[str]) -> list["BaseTool"]:
        """将工具从延迟状态提升为已发现。同时标记缓存为 stale。

        Args:
            names: 要提升的工具名称列表

        Returns:
            新发现的 BaseTool 列表
        """
        newly_discovered: list["BaseTool"] = []
        for name in names:
            if name in self._tool_map and name not in self._discovered_names:
                self._discovered_names.add(name)
                newly_discovered.append(self._tool_map[name])

        if newly_discovered:
            self.stale = True
            logger.info(
                "[DeferredToolManager] Discovered %d tools: %s (session %s)",
                len(newly_discovered),
                [t.name for t in newly_discovered],
                self._session_id,
            )

        return newly_discovered

    def is_discovered(self, name: str) -> bool:
        """检查工具是否已发现"""
        return name in self._discovered_names

    def get_tool(self, name: str) -> Optional["BaseTool"]:
        """按名称获取工具（无论是否已发现）"""
        return self._tool_map.get(name)

    def get_stats(self) -> dict:
        """返回统计信息"""
        return {
            "total_deferred": self.total_deferred,
            "discovered": self.discovered_count,
            "remaining": self.remaining_count,
            "session_id": self._session_id,
        }


# ---------------------------------------------------------------------------
# Store persistence helpers
# ---------------------------------------------------------------------------

_DISCOVERED_TOOLS_NAMESPACE = ("deferred_tools",)
_DISCOVERED_TOOLS_KEY_PREFIX = "session:"


def _store_key_for_session(session_id: str) -> str:
    return f"{_DISCOVERED_TOOLS_KEY_PREFIX}{session_id}"


async def restore_discovered_tools(
    session_id: str,
) -> list[str]:
    """从 BaseStore 恢复上次已发现的工具名列表。失败时返回空列表。"""
    try:
        from src.infra.storage.mongodb_store import create_store

        store = create_store()
        if store is None:
            return []

        item = await store.aget(
            _DISCOVERED_TOOLS_NAMESPACE,
            _store_key_for_session(session_id),
        )
        if item is None:
            return []

        value = item.value
        # value 格式: {"names": [...]}
        if isinstance(value, dict):
            names = value.get("names", [])
        elif isinstance(value, list):
            names = value
        else:
            return []
        return [n for n in names if isinstance(n, str)]
    except Exception:
        logger.warning(
            "[DeferredToolManager] Failed to restore discovered tools for session %s",
            session_id,
            exc_info=True,
        )
        return []


async def persist_discovered_tools(
    session_id: str,
    discovered_names: list[str],
) -> None:
    """将已发现工具名列表持久化到 BaseStore。失败时静默忽略。"""
    if not discovered_names:
        return
    try:
        from src.infra.storage.mongodb_store import create_store

        store = create_store()
        if store is None:
            return

        await store.aput(
            _DISCOVERED_TOOLS_NAMESPACE,
            _store_key_for_session(session_id),
            {"names": discovered_names},
        )
        logger.debug(
            "[DeferredToolManager] Persisted %d discovered tools for session %s",
            len(discovered_names),
            session_id,
        )
    except Exception:
        logger.warning(
            "[DeferredToolManager] Failed to persist discovered tools for session %s",
            session_id,
            exc_info=True,
        )


async def clear_discovered_tools(session_id: str) -> None:
    """清除指定 session 的已发现工具记录。"""
    try:
        from src.infra.storage.mongodb_store import create_store

        store = create_store()
        if store is None:
            return

        await store.aput(
            _DISCOVERED_TOOLS_NAMESPACE,
            _store_key_for_session(session_id),
            None,  # type: ignore[arg-type]  # value=None means delete
        )
    except Exception:
        logger.warning(
            "[DeferredToolManager] Failed to clear discovered tools for session %s",
            session_id,
            exc_info=True,
        )
