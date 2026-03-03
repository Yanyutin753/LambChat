"""
Writer 模块 - 统一流式输出 + 事件存储

提供统一的流式输出接口，对齐前后端事件格式。
所有 Agent 都应该使用这个模块来发送事件给前端。
支持自动保存所有 SSE 事件到 MongoDB（按 trace_id 聚合）。

事件类型 (对齐前端):
- metadata: 会话元数据
- message:chunk: 文本片段 (纯文本)
- thinking: 思考过程
- tool:start: 工具调用开始
- tool:result: 工具调用结果
- agent:call: 调用子 Agent
- agent:result: 子 Agent 返回结果
- observation: 观察/状态更新
- workflow:step: 工作流步骤
- done: 流结束
- error: 错误
"""

import json
import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, AsyncGenerator, Dict, List, Optional

if TYPE_CHECKING:
    from src.infra.session.dual_writer import DualEventWriter

logger = logging.getLogger(__name__)


def _get_timestamp() -> str:
    """获取 ISO 格式时间戳"""
    return datetime.now(timezone.utc).isoformat()


def _generate_trace_id() -> str:
    """生成唯一 trace_id (时间戳 + 完整 UUID，确保不重复)"""
    ts = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S%f")
    return f"trace_{ts}_{uuid.uuid4().hex}"


def _generate_run_id() -> str:
    """生成唯一 run_id (时间戳 + 完整 UUID，用于 LangSmith 关联)"""
    ts = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S%f")
    return f"run_{ts}_{uuid.uuid4().hex}"


@dataclass
class PresenterConfig:
    """Presenter 配置"""

    session_id: Optional[str] = None
    agent_id: Optional[str] = None
    agent_name: str = "Agent"
    user_id: Optional[str] = None  # 用户 ID，用于绑定 session
    run_id: Optional[str] = None  # 运行 ID
    trace_id: Optional[str] = None  # Trace ID (自动生成或手动指定)
    chunk_delay: float = 0.0  # 流式输出延迟 (秒)
    max_result_length: int = 2000  # 结果最大长度
    enable_storage: bool = True  # 是否启用事件存储


class Presenter:
    """
    统一输出展示器 + 事件存储

    所有流式事件按 trace_id 聚合保存到 MongoDB。

    用法:
        presenter = Presenter(config)

        # 方式1: 只构建事件 (同步)
        event = presenter.present_text("Hello")
        yield event

        # 方式2: 构建并保存事件 (异步)
        event = presenter.present_text("Hello")
        await presenter.save_event(event)
        yield event

        # 方式3: 使用 emit_* 方法 (一步完成)
        async for event in presenter.emit_text("Hello"):
            yield event
    """

    def __init__(self, config: Optional[PresenterConfig] = None):
        self.config = config or PresenterConfig()
        self._tool_calls: List[Dict] = []
        self._step_count: int = 0
        self._dual_writer: "DualEventWriter | None" = None
        self._trace_created: bool = False
        self._completed: bool = False

    @property
    def trace_id(self) -> str:
        """获取 trace_id (延迟生成)"""
        if not self.config.trace_id:
            self.config.trace_id = _generate_trace_id()
        return self.config.trace_id

    @property
    def run_id(self) -> str:
        """获取 run_id (延迟生成，用于 LangSmith 关联)"""
        if not self.config.run_id:
            self.config.run_id = _generate_run_id()
        return self.config.run_id

    def get_langsmith_url(self) -> Optional[str]:
        """获取 LangSmith trace URL"""
        import os

        if os.getenv("LANGSMITH_TRACING", "false").lower() != "true":
            return None

        project = os.getenv("LANGSMITH_PROJECT", "default")
        return f"https://smith.langchain.com/o/default/projects/p/{project}/r/{self.run_id}"

    async def _get_dual_writer(self):
        """延迟获取 DualEventWriter"""
        if self._dual_writer is None:
            try:
                from src.infra.session.dual_writer import get_dual_writer

                self._dual_writer = get_dual_writer()
                logger.debug("dual_writer initialized: %s", self._dual_writer is not None)
            except Exception as e:
                logger.warning("Failed to init dual_writer: %s", e)
        return self._dual_writer

    async def _ensure_trace(self):
        """确保 trace 已创建"""
        if self._trace_created:
            return

        dual_writer = await self._get_dual_writer()
        if not dual_writer:
            logger.debug("_ensure_trace: dual_writer is None, skipping")
            return

        # 如果没有 session_id，跳过 trace 创建
        if not self.config.session_id:
            logger.debug(
                "_ensure_trace: no session_id (config.session_id=%s), skipping",
                self.config.session_id,
            )
            return

        try:
            logger.debug(
                "Creating trace: trace_id=%s, session_id=%s",
                self.trace_id,
                self.config.session_id,
            )
            await dual_writer.create_trace(
                trace_id=self.trace_id,
                session_id=self.config.session_id,
                agent_id=self.config.agent_id,
                run_id=self.run_id,
                user_id=self.config.user_id,
                metadata={
                    "agent_name": self.config.agent_name,
                },
            )
            self._trace_created = True
            logger.debug("Trace created successfully: %s", self.trace_id)
        except Exception as e:
            logger.warning("Failed to create trace: %s", e)

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
        # 保持 dict 格式，不做 json.dumps
        return {"event": event, "data": data}

    # ==================== 事件存储方法 ====================

    async def save_event(self, event: Dict[str, Any]) -> None:
        """
        保存 SSE 事件到 Redis + MongoDB (按 trace 聚合)

        Args:
            event: SSE 事件字典，包含 event 和 data 字段
        """
        if not self.config.enable_storage:
            return

        try:
            await self._ensure_trace()

            event_type = event.get("event", "unknown")
            data = event.get("data", {})

            # 如果 data 是字符串（旧格式或外部传入），需要解析并清理
            # 如果是 dict（来自优化后的 _build_event），已经 sanitize 过，直接使用
            if isinstance(data, str):
                try:
                    data = json.loads(data)
                except json.JSONDecodeError:
                    data = {"raw": data}
                data = self._sanitize_for_json(data)

            dual_writer = await self._get_dual_writer()
            if dual_writer and self.config.session_id:
                await dual_writer.write_event(
                    session_id=self.config.session_id,
                    event_type=event_type,
                    data=data,
                    trace_id=self.trace_id,
                    agent_id=self.config.agent_id,
                    run_id=self.run_id,
                )
        except Exception as e:
            logger.warning("Failed to save event: %s", e)

    async def complete(self, status: str = "completed") -> None:
        """
        标记 trace 完成

        应该在流结束时调用此方法。
        会先刷新 MongoDB 写入缓冲，确保所有事件已持久化。

        Args:
            status: 完成状态 (completed/error)
        """
        if self._completed:
            return

        dual_writer = await self._get_dual_writer()
        if dual_writer and self.config.session_id:
            try:
                # 先刷新 MongoDB 缓冲，确保所有事件已写入
                await dual_writer.flush_mongo_buffer()
                await dual_writer.complete_trace(
                    trace_id=self.trace_id,
                    status=status,
                    metadata={
                        "step_count": self._step_count,
                        "tool_calls": len(self._tool_calls),
                    },
                )
                self._completed = True
                logger.debug("Trace completed: %s, status=%s", self.trace_id, status)
            except Exception as e:
                logger.warning("Failed to complete trace %s: %s", self.trace_id, e)

    async def emit(self, event: Dict[str, Any]) -> Dict[str, Any]:
        """发送单个事件（自动保存）"""
        await self.save_event(event)
        return event

    # ==================== 核心输出方法 (同步构建) ====================

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
                "timestamp": _get_timestamp(),
            },
        )

    def present_text(
        self, content: str, depth: int = 0, agent_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """输出文本内容 (单个事件)

        Args:
            content: 文本内容
            depth: 层级深度（0=主代理，1+=子代理）
            agent_id: 代理ID（用于子代理事件）
        """
        return self._build_event(
            "message:chunk",
            {
                "content": content,
                "timestamp": _get_timestamp(),
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
                "agent_id": agent_id or self.config.agent_id,
                "timestamp": _get_timestamp(),
            },
            depth=depth,
            agent_id=agent_id,
        )

    def present_observation(
        self,
        title: str,
        content: Any,
        observation_type: str = "info",
        depth: int = 0,
        agent_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """输出观察/状态更新

        Args:
            title: 标题
            content: 内容
            observation_type: 类型
            depth: 层级深度（0=主代理，1+=子代理）
            agent_id: 代理ID（用于子代理事件）
        """
        return self._build_event(
            "observation",
            {
                "title": title,
                "content": content,
                "type": observation_type,
                "timestamp": _get_timestamp(),
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
                "agent_id": agent_id,
                "agent_name": agent_name,
                "input": input_message[:500],
                "timestamp": _get_timestamp(),
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
    ) -> Dict[str, Any]:
        """输出子 Agent 返回结果

        Args:
            agent_id: 子代理ID
            result: 返回结果
            success: 是否成功
            depth: 层级深度（默认为1，因为这是子代理）
        """
        return self._build_event(
            "agent:result",
            {
                "agent_id": agent_id,
                "result": result,
                "success": success,
                "timestamp": _get_timestamp(),
            },
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
        self._tool_calls.append({"name": tool_name, "input": tool_input})
        return self._build_event(
            "tool:start",
            {
                "tool": tool_name,
                "args": (tool_input if isinstance(tool_input, dict) else {"input": tool_input}),
                "tool_call_id": tool_call_id,
                "timestamp": _get_timestamp(),
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
            "timestamp": _get_timestamp(),
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
                "timestamp": _get_timestamp(),
            },
            depth=depth,
            agent_id=agent_id,
        )

    def present_workflow_step(
        self,
        step_name: str,
        step_id: Optional[str] = None,
        status: str = "running",
        result: Optional[str] = None,
        depth: int = 0,
        agent_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """输出工作流步骤

        Args:
            step_name: 步骤名称
            step_id: 步骤ID
            status: 状态
            result: 结果
            depth: 层级深度（0=主代理，1+=子代理）
            agent_id: 代理ID（用于子代理事件）
        """
        event_type = "workflow:step_start" if status == "running" else "workflow:step_end"
        data = {
            "step_id": step_id or step_name,
            "step_name": step_name,
            "status": status,
            "timestamp": _get_timestamp(),
        }
        if result:
            data["result"] = result[: self.config.max_result_length]
        return self._build_event(event_type, data, depth=depth, agent_id=agent_id)

    def present_code(
        self,
        code: str,
        language: str = "python",
        filename: Optional[str] = None,
        depth: int = 0,
        agent_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """输出代码块

        Args:
            code: 代码内容
            language: 语言
            filename: 文件名
            depth: 层级深度（0=主代理，1+=子代理）
            agent_id: 代理ID（用于子代理事件）
        """
        return self._build_event(
            "code",
            {
                "language": language,
                "code": code,
                "filename": filename,
                "timestamp": _get_timestamp(),
            },
            depth=depth,
            agent_id=agent_id,
        )

    def present_file(
        self,
        path: str,
        action: str = "created",
        content_preview: Optional[str] = None,
        depth: int = 0,
        agent_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """输出文件操作

        Args:
            path: 文件路径
            action: 操作类型
            content_preview: 内容预览
            depth: 层级深度（0=主代理，1+=子代理）
            agent_id: 代理ID（用于子代理事件）
        """
        return self._build_event(
            "file",
            {
                "path": path,
                "action": action,
                "preview": content_preview[:500] if content_preview else None,
                "timestamp": _get_timestamp(),
            },
            depth=depth,
            agent_id=agent_id,
        )

    def present_user_message(
        self, content: str, attachments: Optional[List[Dict[str, Any]]] = None
    ) -> Dict[str, Any]:
        """输出用户消息"""
        data: Dict[str, Any] = {"content": content, "timestamp": _get_timestamp()}
        if attachments:
            data["attachments"] = attachments
        return self._build_event("user:message", data)

    def present_sandbox_starting(self) -> Dict[str, Any]:
        """输出沙箱开始初始化"""
        return self._build_event(
            "sandbox:starting",
            {"timestamp": _get_timestamp()},
        )

    def present_sandbox_state(self, state: str) -> Dict[str, Any]:
        """输出沙箱状态更新

        Args:
            state: 沙箱状态（如 creating, restoring, starting, running 等）
        """
        return self._build_event(
            "sandbox:state",
            {"state": state, "timestamp": _get_timestamp()},
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
                "timestamp": _get_timestamp(),
            },
        )

    def present_sandbox_error(self, error: str) -> Dict[str, Any]:
        """输出沙箱初始化错误

        Args:
            error: 错误信息
        """
        return self._build_event(
            "sandbox:error",
            {"error": error, "timestamp": _get_timestamp()},
        )

    def present_token_usage(
        self,
        input_tokens: int = 0,
        output_tokens: int = 0,
        total_tokens: int = 0,
        duration: float = 0.0,
    ) -> Dict[str, Any]:
        """输出 Token 使用统计

        Args:
            input_tokens: 输入 token 数
            output_tokens: 输出 token 数
            total_tokens: 总 token 数
            duration: 对话耗时（秒）
        """
        return self._build_event(
            "token:usage",
            {
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "total_tokens": total_tokens,
                "duration": duration,
                "timestamp": _get_timestamp(),
            },
        )

    def done(self) -> Dict[str, Any]:
        """输出流结束标记"""
        return self._build_event(
            "done",
            {
                "status": "completed",
                "trace_id": self.trace_id,
                "steps": self._step_count,
                "tool_calls": len(self._tool_calls),
                "timestamp": _get_timestamp(),
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
                "timestamp": _get_timestamp(),
            },
        )

    # ==================== 异步流式输出方法 (构建 + 保存) ====================

    async def emit_text(self, content: str) -> Dict[str, Any]:
        """输出文本并保存事件"""
        event = self.present_text(content)
        await self.save_event(event)
        return event

    async def stream_text(
        self, content: str, chunk_size: int = 0
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        流式输出文本 (逐字/逐块) 并保存

        Args:
            content: 完整文本
            chunk_size: 分块大小，0 表示按字符输出
        """
        import asyncio

        if chunk_size == 0:
            for char in content:
                event = await self.emit_text(char)
                yield event
                if self.config.chunk_delay > 0:
                    await asyncio.sleep(self.config.chunk_delay)
        else:
            for i in range(0, len(content), chunk_size):
                chunk = content[i : i + chunk_size]
                event = await self.emit_text(chunk)
                yield event
                if self.config.chunk_delay > 0:
                    await asyncio.sleep(self.config.chunk_delay)

    async def emit_thinking(self, content: str) -> Dict[str, Any]:
        """输出思考过程并保存"""
        event = self.present_thinking(content)
        await self.save_event(event)
        return event

    async def emit_user_message(
        self, content: str, attachments: Optional[List[Dict[str, Any]]] = None
    ) -> Dict[str, Any]:
        """输出用户消息并保存"""
        event = self.present_user_message(content, attachments)
        await self.save_event(event)
        return event

    async def emit_sandbox_starting(self) -> Dict[str, Any]:
        """输出沙箱开始初始化并保存"""
        event = self.present_sandbox_starting()
        await self.save_event(event)
        return event

    async def emit_sandbox_state(self, state: str) -> Dict[str, Any]:
        """输出沙箱状态更新并保存"""
        event = self.present_sandbox_state(state)
        await self.save_event(event)
        return event

    async def emit_sandbox_ready(
        self,
        sandbox_id: str,
        work_dir: Optional[str] = None,
    ) -> Dict[str, Any]:
        """输出沙箱就绪并保存"""
        event = self.present_sandbox_ready(sandbox_id, work_dir)
        await self.save_event(event)
        return event

    async def emit_sandbox_error(self, error: str) -> Dict[str, Any]:
        """输出沙箱初始化错误并保存"""
        event = self.present_sandbox_error(error)
        await self.save_event(event)
        return event

    async def emit_token_usage(
        self,
        input_tokens: int = 0,
        output_tokens: int = 0,
        total_tokens: int = 0,
        duration: float = 0.0,
    ) -> Dict[str, Any]:
        """输出 Token 使用统计并保存"""
        event = self.present_token_usage(input_tokens, output_tokens, total_tokens, duration)
        await self.save_event(event)
        return event


# ==================== 便捷函数 ====================


def create_presenter(
    session_id: str = "default",
    agent_id: str = "default",
    agent_name: str = "Agent",
    run_id: Optional[str] = None,
    trace_id: Optional[str] = None,
    user_id: Optional[str] = None,
) -> Presenter:
    """创建 Presenter 实例"""
    config = PresenterConfig(
        session_id=session_id,
        agent_id=agent_id,
        agent_name=agent_name,
        run_id=run_id,
        trace_id=trace_id,
        user_id=user_id,
    )
    return Presenter(config)
