"""Presenter 同步事件构建方法 (Mixin)

所有 present_* 方法均为纯数据构建，无 IO 操作。
通过 self._build_event() 和 self.config 访问主类状态。
"""

from __future__ import annotations

from itertools import islice
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Sequence

from src.infra.utils.datetime import utc_now_iso
from src.infra.writer.presenter_config import _bounded_attachments

if TYPE_CHECKING:
    from src.infra.writer.presenter_config import PresenterConfig

TOOL_START_ARG_MAX_STRING_CHARS = 2_000
TOOL_START_ARG_MAX_LIST_ITEMS = 100
TOOL_START_ARG_MAX_DICT_ITEMS = 100
TOOL_START_ARG_MAX_DEPTH = 8


def _compact_tool_start_arg(value: Any, *, depth: int = 0) -> Any:
    if depth >= TOOL_START_ARG_MAX_DEPTH:
        return "[truncated: max depth exceeded]"

    if isinstance(value, str):
        if len(value) <= TOOL_START_ARG_MAX_STRING_CHARS:
            return value
        return (
            value[:TOOL_START_ARG_MAX_STRING_CHARS].rstrip()
            + f"\n[truncated from {len(value)} chars]"
        )

    if isinstance(value, dict):
        compacted: dict[Any, Any] = {}
        for key in islice(value, TOOL_START_ARG_MAX_DICT_ITEMS):
            compacted[key] = _compact_tool_start_arg(value[key], depth=depth + 1)
        omitted = len(value) - TOOL_START_ARG_MAX_DICT_ITEMS
        if omitted > 0:
            compacted["_truncated_keys"] = omitted
        return compacted

    if isinstance(value, (list, tuple)):
        items = [
            _compact_tool_start_arg(item, depth=depth + 1)
            for item in value[:TOOL_START_ARG_MAX_LIST_ITEMS]
        ]
        omitted = len(value) - TOOL_START_ARG_MAX_LIST_ITEMS
        if omitted > 0:
            items.append({"_truncated_items": omitted})
        return items

    return value


class EventPresenterMixin:
    """同步事件构建 mixin —— 挂载到 Presenter 后可访问 self.config / self._step_count 等。"""

    # Attributes provided by the Presenter host class
    config: PresenterConfig
    trace_id: str
    run_id: str
    _step_count: int
    _tool_calls: list[dict[str, Any]]

    # ------------------------------------------------------------------
    # 内部工具
    # ------------------------------------------------------------------

    def _sanitize_for_json(self, obj: Any) -> Any:
        """递归清理对象，移除不可序列化的内容"""
        if obj is None or isinstance(obj, (str, int, float, bool)):
            return obj
        if isinstance(obj, dict):
            return {k: self._sanitize_for_json(v) for k, v in obj.items()}
        if isinstance(obj, (list, tuple)):
            return [self._sanitize_for_json(item) for item in obj]
        # 其他类型（如 ToolRuntime, datetime 等）转为字符串
        return str(obj)

    def _build_event(
        self, event: str, data: Any, depth: int = 0, agent_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """构建 SSE 事件

        内部保持 data 为 dict 格式，避免多次 JSON 序列化/反序列化。
        仅在 Redis 写入边界做一次 json.dumps。

        Args:
            event: 事件类型
            data: 事件数据
            depth: 层级深度（0=主代理，1+=子代理）
            agent_id: 代理ID（用于子代理事件）
        """
        if isinstance(data, str):
            return {"event": event, "data": data}

        data = self._sanitize_for_json(data)
        if isinstance(data, dict):
            if depth > 0:
                data["depth"] = depth
            if agent_id:
                data["agent_id"] = agent_id
            elif "agent_id" not in data:
                data["agent_id"] = self.config.agent_id
        # 保持 dict 格式，不做 json.dumps
        return {"event": event, "data": data}

    # ------------------------------------------------------------------
    # 事件构建方法
    # ------------------------------------------------------------------

    def metadata(self) -> Dict[str, Any]:
        """发送会话元数据"""
        return self._build_event(
            "metadata",
            {
                "session_id": self.config.session_id,
                "agent_id": self.config.agent_id,
                "agent_name": self.config.agent_name,
                "trace_id": self.trace_id,
                "run_id": self.run_id,
                "timestamp": utc_now_iso(),
            },
        )

    def present_text(
        self,
        content: str,
        text_id: Optional[str] = None,
        depth: int = 0,
        agent_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """输出文本内容 (单个事件)

        Args:
            content: 文本内容
            text_id: 文本块的唯一标识（用于前端合并同一块的多个事件）
            depth: 层级深度（0=主代理，1+=子代理）
            agent_id: 代理ID（用于子代理事件）
        """
        return self._build_event(
            "message:chunk",
            {
                "content": content,
                "text_id": text_id,
                "timestamp": utc_now_iso(),
            },
            depth=depth,
            agent_id=agent_id,
        )

    def present_summary(
        self,
        content: str,
        summary_id: Optional[str] = None,
        depth: int = 0,
        agent_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """输出总结/意图信息（来自 summarization 事件）

        Args:
            content: 总结文本
            summary_id: 唯一标识（用于前端合并多个 chunk）
            depth: 层级深度（0=主代理，1+=子代理）
            agent_id: 代理ID（用于子代理事件）
        """
        return self._build_event(
            "summary",
            {
                "content": content,
                "summary_id": summary_id,
                "timestamp": utc_now_iso(),
            },
            depth=depth,
            agent_id=agent_id,
        )

    def present_recommend_questions(
        self,
        questions: Sequence[str | Dict[str, Any]],
        depth: int = 0,
        agent_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """输出推荐追问列表.

        Args:
            questions: 推荐问题列表。每项可为字符串，或包含 content/text/upload 的字典。
            depth: 层级深度（0=主代理，1+=子代理）
            agent_id: 代理ID（用于子代理事件）
        """
        return self._build_event(
            "recommend:questions",
            {
                "questions": questions,
                "timestamp": utc_now_iso(),
            },
            depth=depth,
            agent_id=agent_id,
        )

    def present_thinking(
        self,
        content: str,
        thinking_id: Optional[str] = None,
        depth: int = 0,
        agent_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """输出思考过程

        Args:
            content: 思考内容
            thinking_id: thinking 块的唯一标识（用于前端合并同一块的多个事件）
            depth: 层级深度（0=主代理，1+=子代理）
            agent_id: 代理ID（用于子代理事件）
        """
        return self._build_event(
            "thinking",
            {
                "content": content,
                "thinking_id": thinking_id,
                "timestamp": utc_now_iso(),
            },
            depth=depth,
            agent_id=agent_id,
        )

    def present_todo(
        self,
        todos: list[dict[str, Any]],
        depth: int = 0,
        agent_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """输出任务列表更新

        Args:
            todos: 任务列表，每项包含 content, status, activeForm
            depth: 层级深度（0=主代理，1+=子代理）
            agent_id: 代理ID（用于子代理事件）
        """
        return self._build_event(
            "todo:updated",
            {
                "todos": todos,
                "timestamp": utc_now_iso(),
            },
            depth=depth,
            agent_id=agent_id,
        )

    def present_agent_call(
        self,
        agent_id: str,
        agent_name: str,
        input_message: str,
        depth: int = 1,
        agent_avatar: Optional[str] = None,
    ) -> Dict[str, Any]:
        """输出子 Agent 调用

        Args:
            agent_id: 子代理ID
            agent_name: 子代理名称
            input_message: 输入消息
            depth: 层级深度（默认为1，因为这是子代理）
        """
        self._step_count += 1
        return self._build_event(
            "agent:call",
            {
                "step": self._step_count,
                "agent_name": agent_name,
                "agent_avatar": agent_avatar,
                "input": input_message,
                "timestamp": utc_now_iso(),
            },
            depth=depth,
            agent_id=agent_id,
        )

    def present_agent_result(
        self,
        agent_id: str,
        result: str,
        success: bool = True,
        depth: int = 1,
        error: Optional[str] = None,
    ) -> Dict[str, Any]:
        """输出子 Agent 返回结果

        Args:
            agent_id: 子代理ID
            result: 返回结果
            success: 是否成功
            depth: 层级深度（默认为1，因为这是子代理）
            error: 错误信息（如果有）
        """
        data: Dict[str, Any] = {
            "result": result,
            "success": success,
            "timestamp": utc_now_iso(),
        }
        if error:
            data["error"] = error
        return self._build_event(
            "agent:result",
            data,
            depth=depth,
            agent_id=agent_id,
        )

    def present_tool_start(
        self,
        tool_name: str,
        tool_input: Any,
        tool_call_id: Optional[str] = None,
        depth: int = 0,
        agent_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """输出工具调用开始

        Args:
            tool_name: 工具名称
            tool_input: 工具输入
            tool_call_id: 工具调用唯一ID
            depth: 层级深度（0=主代理，1+=子代理）
            agent_id: 代理ID（用于子代理事件）
        """
        self._tool_calls.append({"name": tool_name})
        args = tool_input if isinstance(tool_input, dict) else {"input": tool_input}
        return self._build_event(
            "tool:start",
            {
                "tool": tool_name,
                "args": _compact_tool_start_arg(args),
                "tool_call_id": tool_call_id,
                "timestamp": utc_now_iso(),
            },
            depth=depth,
            agent_id=agent_id,
        )

    def present_tool_result(
        self,
        tool_name: str,
        result: Any,
        tool_call_id: Optional[str] = None,
        success: bool = True,
        error: Optional[str] = None,
        depth: int = 0,
        agent_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """输出工具调用结果

        Args:
            tool_name: 工具名称
            result: 工具结果
            tool_call_id: 工具调用唯一ID
            success: 是否成功
            error: 错误信息（如果有）
            depth: 层级深度（0=主代理，1+=子代理）
            agent_id: 代理ID（用于子代理事件）
        """
        data: Dict[str, Any] = {
            "tool": tool_name,
            "result": result,
            "success": success,
            "timestamp": utc_now_iso(),
        }
        if tool_call_id:
            data["tool_call_id"] = tool_call_id
        if error:
            data["error"] = error
        return self._build_event(
            "tool:result",
            data,
            depth=depth,
            agent_id=agent_id,
        )

    def present_artifact_result(
        self,
        artifact: Dict[str, Any],
        *,
        success: bool = True,
        error: Optional[str] = None,
        depth: int = 0,
        agent_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """输出用户可见产物结果，不渲染成工具调用。"""
        data: Dict[str, Any] = {
            "artifact": artifact,
            "success": success,
            "timestamp": utc_now_iso(),
        }
        if error:
            data["error"] = error
        return self._build_event(
            "artifact:result",
            data,
            depth=depth,
            agent_id=agent_id,
        )

    def present_ask_human(
        self,
        approval_id: str,
        question: str,
        question_type: str = "text",
        choices: Optional[List[str]] = None,
        default: Optional[str] = None,
        depth: int = 0,
        agent_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """输出人工输入请求

        当 Agent 调用 ask_human 工具时，发送此事件通知前端。

        Args:
            approval_id: 审批 ID，前端响应时使用
            question: 向用户提出的问题
            question_type: 问题类型 (text, confirm, choice)
            choices: 选项列表 (choice 类型时使用)
            default: 默认值
            depth: 层级深度（0=主代理，1+=子代理）
            agent_id: 代理ID（用于子代理事件）
        """
        return self._build_event(
            "approval_required",
            {
                "id": approval_id,
                "message": question,
                "type": question_type,
                "choices": choices or [],
                "default": default,
                "timestamp": utc_now_iso(),
            },
            depth=depth,
            agent_id=agent_id,
        )

    def present_user_message(
        self,
        content: str,
        attachments: Optional[List[Dict[str, Any]]] = None,
        message_id: Optional[str] = None,
        enabled_skills: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """输出用户消息"""
        resolved_message_id = message_id or f"{self.run_id}:user"
        data: Dict[str, Any] = {
            "content": content,
            "timestamp": utc_now_iso(),
            "message_id": resolved_message_id,
            "run_id": self.run_id,
        }
        data["attachments"] = _bounded_attachments(attachments)
        if enabled_skills:
            data["enabled_skills"] = enabled_skills
        return self._build_event("user:message", data)

    def present_sandbox_starting(self) -> Dict[str, Any]:
        """输出沙箱开始初始化"""
        return self._build_event(
            "sandbox:starting",
            {"timestamp": utc_now_iso()},
        )

    def present_sandbox_ready(
        self,
        sandbox_id: str,
        work_dir: Optional[str] = None,
    ) -> Dict[str, Any]:
        """输出沙箱就绪

        Args:
            sandbox_id: 沙箱ID
            work_dir: 工作目录
        """
        return self._build_event(
            "sandbox:ready",
            {
                "sandbox_id": sandbox_id,
                "work_dir": work_dir,
                "timestamp": utc_now_iso(),
            },
        )

    def present_sandbox_error(self, error: str) -> Dict[str, Any]:
        """输出沙箱初始化错误

        Args:
            error: 错误信息
        """
        return self._build_event(
            "sandbox:error",
            {"error": error, "timestamp": utc_now_iso()},
        )

    def present_token_usage(
        self,
        input_tokens: int = 0,
        output_tokens: int = 0,
        total_tokens: int = 0,
        duration: float = 0.0,
        cache_creation_tokens: int = 0,
        cache_read_tokens: int = 0,
        model_id: str | None = None,
        model: str | None = None,
    ) -> Dict[str, Any]:
        """输出 Token 使用统计

        Args:
            input_tokens: 输入 token 数
            output_tokens: 输出 token 数
            total_tokens: 总 token 数
            duration: 对话耗时（秒）
            cache_creation_tokens: 缓存创建 token 数
            cache_read_tokens: 缓存读取 token 数
            model_id: 模型配置 ID
            model: 原始模型值
        """
        data: Dict[str, Any] = {
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": total_tokens,
            "duration": duration,
            "timestamp": utc_now_iso(),
        }
        # 添加缓存token统计（如果有）
        if cache_creation_tokens > 0:
            data["cache_creation_tokens"] = cache_creation_tokens
        if cache_read_tokens > 0:
            data["cache_read_tokens"] = cache_read_tokens
        if model_id:
            data["model_id"] = model_id
        if model:
            data["model"] = model
        return self._build_event("token:usage", data)

    def present_skills_changed(
        self,
        action: str = "updated",
        skill_name: Optional[str] = None,
        files_count: int = 0,
    ) -> Dict[str, Any]:
        """输出 Skills 变更通知

        通知前端 skills 列表已发生变更，需要刷新。

        Args:
            action: 变更类型 ("created", "updated", "deleted")
            skill_name: 变更的 skill 名称（可选）
            files_count: 变更涉及的文件数量
        """
        data: Dict[str, Any] = {
            "action": action,
            "files_count": files_count,
            "timestamp": utc_now_iso(),
        }
        if skill_name:
            data["skill_name"] = skill_name
        return self._build_event("skills:changed", data)

    def done(self) -> Dict[str, Any]:
        """输出流结束标记"""
        return self._build_event(
            "done",
            {
                "status": "completed",
                "trace_id": self.trace_id,
                "steps": self._step_count,
                "tool_calls": len(self._tool_calls),
                "timestamp": utc_now_iso(),
            },
        )

    def error(
        self,
        message: str,
        error_type: str = "Error",
        details: Optional[Dict] = None,
    ) -> Dict[str, Any]:
        """输出错误"""
        return self._build_event(
            "error",
            {
                "error": message,
                "type": error_type,
                "trace_id": self.trace_id,
                "details": details,
                "timestamp": utc_now_iso(),
            },
        )
