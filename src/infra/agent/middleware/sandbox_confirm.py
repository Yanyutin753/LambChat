"""SandboxConfirmMiddleware：本地沙箱确认门（ToolNode 包裹层，整批单次中断）。

背景（2026-09-06 线上复盘）：此前确认门在 LocalSandboxBackend 的每个执行/
写/上传入口各自 interrupt——并行工具场景下恢复值按中断序号匹配会**串用**
（给 A 的批准可能被 B 消费），且 N 条并行命令要 N 轮挂起-恢复、每轮给剩余
工具重新物化审批卡（已确认过的命令再次弹卡）。

本中间件把门上移一层，在 ToolNode 调用工具**之前**拦截：

- 同批（同一条 AIMessage 的 tool_calls）需要确认的操作**一次 interrupt**
  覆盖全部，审批卡一条列出 N 项；用户批准后 memo（本批已决）直通其余
  调用——不再有第二轮挂起，恢复值不可能串用；
- 恢复重放时 memo 不跨 checkpoint，第一个调用重放 interrupt() 直接返回
  既定批复值，memo 重建，其余调用照常直通；
- 图不支持 interrupt（无 checkpointer）fail-closed 拒绝；
- 读类工具与 policy=none/未命中命令直通。

门位在模型可见的工具边界（与「一次执行一张卡」语义同层）；后端
LocalSandboxBackend 保持纯执行器（env 注入等不变）。
"""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from typing import Any

from langchain.agents.middleware.types import AgentMiddleware, ToolCallRequest
from langchain_core.messages import ToolMessage

from src.infra.logging import get_logger
from src.infra.sandbox.confirm import needs_confirm
from src.infra.sandbox.relay.registry import SandboxClientRegistry
from src.kernel.errors import AppError

logger = get_logger(__name__)

# 过门的模型可见工具（本地沙箱执行/写/上传）；读类不确认
CONFIRMABLE_TOOLS = frozenset({"execute", "write_file", "edit_file", "delete", "upload"})

# 操作文案动词（用户可读描述）
_OP_LABELS = {
    "execute": "执行命令",
    "write_file": "写入文件",
    "edit_file": "编辑文件",
    "delete": "删除文件",
    "upload": "上传文件",
}

_EXEC_DESC_MAX_CHARS = 200


def _batch_key(tool_name: str, args: dict[str, Any]) -> tuple[str, str]:
    return tool_name, json.dumps(args, sort_keys=True, ensure_ascii=False, default=str)


def _op_description(tool_name: str, args: dict[str, Any]) -> tuple[str, str]:
    """返回（用户可读描述, 送 needs_confirm 判定的哨兵命令）。"""
    if tool_name == "execute":
        command = str(args.get("command", ""))
        clipped = (
            command
            if len(command) <= _EXEC_DESC_MAX_CHARS
            else command[:_EXEC_DESC_MAX_CHARS] + "…"
        )
        return f"执行命令：{clipped}", command
    if tool_name == "upload":
        files = args.get("files")
        count = len(files) if isinstance(files, list) else 1
        return f"上传 {count} 个文件", f"rm upload {count} files"
    label = _OP_LABELS.get(tool_name, tool_name)
    path = str(args.get("file_path", args.get("path", "")))
    return f"{label}：{path}", f"rm {tool_name} {path}"


async def _lookup_confirm_policy(user_id: str) -> str:
    """本地沙箱策略源：当前活跃 daemon 上报（缺失/故障归 all 保守确认）。"""
    try:
        policy = await SandboxClientRegistry().get_confirm_policy(user_id)
        return policy if policy in ("all", "commands", "none") else "all"
    except Exception:  # noqa: BLE001 - 查询尽力而为，失败保守归 all
        logger.warning("confirm policy lookup failed for user %s; defaulting to all", user_id)
        return "all"


def _user_storage():
    """延迟导入的用户存储工厂（测试替换点）。"""
    from src.infra.user.storage import UserStorage

    return UserStorage()


async def _lookup_cloud_confirm_policy(user_id: str) -> str:
    """云端沙箱策略源：用户 metadata 偏好 sandboxCloudConfirmPolicy。

    未设置/非法值归 none（保持云上隔离环境无确认的历史行为）；用户不存在
    同样归 none；查询异常归 all（与本地门同样保守 fail-closed——静默降级
    放行会绕过用户自己选的更严策略）。
    """
    try:
        user = await _user_storage().get_by_id(user_id)
    except Exception:  # noqa: BLE001 - 查询尽力而为，失败保守归 all
        logger.warning("cloud confirm policy lookup failed for user %s; defaulting to all", user_id)
        return "all"
    value = (getattr(user, "metadata", None) or {}).get("sandboxCloudConfirmPolicy")
    return value if value in ("all", "commands", "none") else "none"


class _RegistryPolicyResolver:
    """本地策略源闭包（daemon 注册表上报，缺失/故障归 all）。"""

    def __init__(self, user_id: str) -> None:
        self._user_id = user_id

    async def __call__(self) -> str:
        return await _lookup_confirm_policy(self._user_id)


class _CloudPolicyResolver:
    """云端策略源（用户 metadata 偏好，未设置归 none）。

    实例内缓存：中间件每次 run 重建，策略按 run 快照——run 内不因偏好
    修改中途变档，也避免每条工具调用都打一次用户表。
    """

    def __init__(self, user_id: str) -> None:
        self._user_id = user_id
        self._policy: str | None = None

    async def __call__(self) -> str:
        if self._policy is None:
            self._policy = await _lookup_cloud_confirm_policy(self._user_id)
        return self._policy


def _last_tool_calls(state: Any) -> list[dict[str, Any]]:
    """从 agent state 取最近一条 AIMessage 的 tool_calls（本批）。"""
    messages = None
    if isinstance(state, dict):
        messages = state.get("messages")
    elif hasattr(state, "messages"):
        messages = state.messages
    if not messages:
        return []
    for msg in reversed(list(messages)):
        tool_calls = getattr(msg, "tool_calls", None)
        if isinstance(tool_calls, list) and tool_calls:
            return [
                {"name": tc.get("name", ""), "args": tc.get("args") or {}, "id": tc.get("id", "")}
                for tc in tool_calls
            ]
    return []


class SandboxConfirmMiddleware(AgentMiddleware):
    """沙箱统一确认门（本地 + 云端全部后端）：整批同消息 interrupt。

    并行工具在 ToolNode 下是**独立图任务**（一个任务挂起不会取消兄弟任务，
    实验验证），且 interrupt 匹配按任务隔离——因此让**每个需确认的调用各自
    interrupt**，但携带**同一份确定性批清单**（来自 checkpoint 的 tool_calls，
    跨任务跨重放一致）：

    - 挂起快照会有 N 个同消息中断 → 物化层（hitl.materialize）按
      origin+message 去重为**一张审批卡**；
    - 恢复时节点侧 expand_sandbox_confirm_resume 把批复值映射到**全部同批
      中断 id** → 所有任务同时拿到决定，各执行恰好一次——无锁、无等待、
      无 resume 值串用。

    ``policy_resolver``：策略源——本地传 daemon 注册表上报（默认），
    云端传 :class:`_CloudPolicyResolver`（用户 metadata 偏好）。
    """

    def __init__(
        self,
        *,
        user_id: str,
        policy_resolver: Callable[[], Awaitable[str]] | None = None,
    ) -> None:
        super().__init__()
        self._user_id = user_id
        self._policy_resolver = policy_resolver or _RegistryPolicyResolver(user_id)

    async def awrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], Awaitable[ToolMessage | Any]],
    ) -> ToolMessage | Any:
        # AppError 护盾：沙箱派发失败（超时/离线/exec_failed 等）转错误
        # ToolMessage——模型看到失败可调整重试，单条命令失败不再击穿整个 run
        # （deepagents ToolNode 不兜工具异常，实验验证）。编程性异常照旧上抛。
        try:
            return await self._awrap_tool_call_inner(request, handler)
        except AppError as exc:
            return self._error_tool_message(request, exc)

    async def _awrap_tool_call_inner(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], Awaitable[ToolMessage | Any]],
    ) -> ToolMessage | Any:
        tool_call = request.tool_call
        tool_name = str(tool_call.get("name", ""))
        if tool_name not in CONFIRMABLE_TOOLS:
            return await handler(request)

        policy = await self._policy_resolver()
        if policy == "none":
            return await handler(request)
        args = tool_call.get("args") or {}
        _, sentinel = _op_description(tool_name, args)
        if not needs_confirm(sentinel, policy):
            return await handler(request)

        # 确定性批清单：本批全部需确认的操作（各并行任务算得同一份）
        batch_listing: list[str] = []
        seen: set[tuple[str, str]] = set()
        for tc in _last_tool_calls(request.state):
            tc_name = str(tc.get("name", ""))
            if tc_name not in CONFIRMABLE_TOOLS:
                continue
            tc_key = _batch_key(tc_name, tc.get("args") or {})
            if tc_key in seen:
                continue
            desc, snt = _op_description(tc_name, tc.get("args") or {})
            if policy == "all" or needs_confirm(snt, policy):
                seen.add(tc_key)
                batch_listing.append(desc)
        if not batch_listing:
            return await handler(request)

        from src.infra.tool.human_tool.runtime import hitl_interrupt_supported

        if not hitl_interrupt_supported.get():
            logger.warning(
                "[SandboxConfirm] interrupt 不可用，按拒绝收敛（fail-closed）: %s",
                "; ".join(batch_listing[:3]),
            )
            return self._declined(request)

        from langgraph.types import interrupt

        message = f"确认在本机执行 {len(batch_listing)} 项操作：\n" + "\n".join(
            f"{i + 1}. {desc}" for i, desc in enumerate(batch_listing)
        )
        resume_value = interrupt(
            {
                "kind": "ask_human",
                # 沙箱确认门标记：历史回放据此跳过 ask_human 工具卡合成
                "origin": "sandbox_confirm",
                "message": message,
                "fields": [],
            }
        )
        approved = bool(isinstance(resume_value, dict) and resume_value.get("approved"))
        return await self._run(request, handler, approved)

    async def _run(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], Awaitable[ToolMessage | Any]],
        approved: bool,
    ) -> ToolMessage | Any:
        if approved:
            return await handler(request)
        return self._declined(request)

    def _error_tool_message(self, request: ToolCallRequest, exc: AppError) -> ToolMessage:
        tool_call = request.tool_call
        return ToolMessage(
            content=exc.display_message,
            tool_call_id=str(tool_call.get("id", "") or ""),
            name=str(tool_call.get("name", "")),
            status="error",
        )

    def _declined(self, request: ToolCallRequest) -> ToolMessage:
        tool_call = request.tool_call
        return ToolMessage(
            content=(
                "Execution declined by user (declined_by_user). "
                "Do not retry the same operation unless the user explicitly asks."
            ),
            tool_call_id=str(tool_call.get("id", "") or ""),
            name=str(tool_call.get("name", "")),
            status="error",
        )
