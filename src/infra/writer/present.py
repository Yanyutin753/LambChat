"""
Writer 模块 - 统一流式输出 + 事件存储

提供统一的流式输出接口，对齐前后端事件格式。
所有 Agent 都应该使用这个模块来发送事件给前端。
支持自动保存所有 SSE 事件到 MongoDB（按 trace_id 聚合）。

事件类型 (对齐前端):
- metadata: 会话元数据
- message:chunk: 文本片段 (纯文本)
- thinking: 思考过程
- recommend:questions: 推荐追问
- tool:start: 工具调用开始
- tool:result: 工具调用结果
- agent:call: 调用子 Agent
- agent:result: 子 Agent 返回结果
- observation: 观察/状态更新
- done: 流结束
- error: 错误
"""

import asyncio
from typing import Any, AsyncGenerator, Dict, List, Optional, Sequence

from src.infra.async_utils.background_tasks import BestEffortTaskLimiter
from src.infra.logging import get_logger
from src.infra.upload.file_record import FileRecordStorage

# Re-export public API for backward compatibility
from src.infra.writer.presenter_config import (  # noqa: F401
    PresenterConfig,
    _extract_attachment_keys,
    _generate_run_id,
    _generate_trace_id,
    should_increment_unread_for_trace_status,
)
from src.infra.writer.presenter_events import EventPresenterMixin  # noqa: F401
from src.infra.writer.presenter_storage import StoragePresenterMixin  # noqa: F401

logger = get_logger(__name__)

_user_message_search_index_tasks = BestEffortTaskLimiter(
    "user-message-search-index",
    max_tasks=64,
)


async def _append_user_message_search_content(session_id: str, content: str) -> None:
    from src.infra.session.storage import SessionStorage

    await SessionStorage().append_user_message_search_content(session_id, content)


def schedule_user_message_search_index(
    session_id: str,
    content: str,
) -> asyncio.Task[None]:
    """Schedule rebuildable session search metadata after the message is durable."""
    return _user_message_search_index_tasks.create_task(
        _append_user_message_search_content(session_id, content)
    )


async def drain_user_message_search_index_tasks() -> None:
    """Drain pending user-message search metadata writes during shutdown."""
    await _user_message_search_index_tasks.drain()


class Presenter(EventPresenterMixin, StoragePresenterMixin):
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
        # HITL interrupt 模式（issue #218）：由 agent 节点在图挂起时置 True，
        # TaskExecutor 据此将会话标记为 WAITING_HUMAN 而非 COMPLETED。
        self.hitl_suspended: bool = False
        self._tool_calls: List[Dict] = []
        self._step_count: int = 0
        self._dual_writer = None
        self._trace_created: bool = False
        self._completed: bool = False
        self._token_usage_recorded: bool = False
        self._done_recorded: bool = False
        self._goal_end_recorded: bool = False
        self._recommend_questions_recorded: bool = False

    @property
    def trace_id(self) -> str:
        """获取 trace_id (延迟生成)"""
        if not self.config.trace_id:
            self.config.trace_id = _generate_trace_id()
        return self.config.trace_id

    @trace_id.setter
    def trace_id(self, value: str) -> None:
        self.config.trace_id = value

    @property
    def run_id(self) -> str:
        """获取 run_id (延迟生成，用于 LangSmith 关联)"""
        if not self.config.run_id:
            self.config.run_id = _generate_run_id()
        return self.config.run_id

    @run_id.setter
    def run_id(self, value: str) -> None:
        self.config.run_id = value

    @property
    def recommend_questions_recorded(self) -> bool:
        """Whether recommended questions were already emitted for this run."""
        return self._recommend_questions_recorded

    def get_langsmith_url(self) -> Optional[str]:
        """获取 LangSmith trace URL"""
        import os

        if os.getenv("LANGSMITH_TRACING", "false").lower() != "true":
            return None

        project = os.getenv("LANGSMITH_PROJECT", "default")
        return f"https://smith.langchain.com/o/default/projects/p/{project}/r/{self.run_id}"

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

    async def emit_recommend_questions(
        self,
        questions: Sequence[str | Dict[str, Any]],
    ) -> Dict[str, Any]:
        """输出推荐追问列表并保存"""
        event = self.present_recommend_questions(questions)
        if self._recommend_questions_recorded:
            return event
        await self.save_event(event)
        self._recommend_questions_recorded = True
        return event

    async def publish_recommend_questions(self, questions: Sequence[str]) -> None:
        """Persist run recommendations and publish them after the SSE stream closes."""
        if self._recommend_questions_recorded:
            return
        normalized = [question.strip() for question in questions if question.strip()][:3]
        if not normalized:
            return

        dual_writer = await self._get_dual_writer()
        if dual_writer and self.config.session_id:
            await dual_writer.set_run_recommend_questions(
                session_id=self.config.session_id,
                run_id=self.run_id,
                questions=normalized,
            )

        if self.config.user_id and self.config.session_id:
            try:
                from src.infra.websocket import get_connection_manager

                await get_connection_manager().send_to_user_with_broadcast(
                    self.config.user_id,
                    {
                        "type": "recommend:questions",
                        "data": {
                            "session_id": self.config.session_id,
                            "run_id": self.run_id,
                            "questions": normalized,
                        },
                    },
                )
            except Exception as exc:
                logger.debug("Failed to publish recommended questions over WebSocket: %s", exc)

        self._recommend_questions_recorded = True

    async def emit_user_message(
        self,
        content: str,
        attachments: Optional[List[Dict[str, Any]]] = None,
        message_id: Optional[str] = None,
        enabled_skills: Optional[List[str]] = None,
        attachment_references_claimed: bool = False,
        schedule_search_index: bool = True,
    ) -> Dict[str, Any]:
        """输出用户消息并保存"""
        attachment_keys = _extract_attachment_keys(attachments)
        file_records: FileRecordStorage | None = None
        claims_established = False
        if attachment_keys:
            file_records = FileRecordStorage()
            if attachment_references_claimed:
                claims_established = True
            else:
                await file_records.claim_owned_references(
                    attachment_keys,
                    self.config.user_id or "",
                )
                claims_established = True

        try:
            event = self.present_user_message(
                content,
                attachments,
                message_id=message_id,
                enabled_skills=enabled_skills,
            )
            await self.save_event(event, raise_on_error=True)
        except (Exception, asyncio.CancelledError):
            if claims_established and file_records is not None:
                try:
                    await file_records.release_owned_references(
                        attachment_keys,
                        self.config.user_id or "",
                    )
                except Exception as rollback_error:
                    logger.error(
                        "Failed to roll back attachment references for user message: %s",
                        rollback_error,
                    )
            raise

        if self.config.session_id and schedule_search_index:
            schedule_user_message_search_index(self.config.session_id, content)
        return event

    async def emit_skills_changed(
        self,
        action: str = "updated",
        skill_name: Optional[str] = None,
        files_count: int = 0,
    ) -> Dict[str, Any]:
        """输出 Skills 变更通知并保存"""
        event = self.present_skills_changed(action, skill_name, files_count)
        await self.save_event(event)
        return event

    async def emit_sandbox_starting(self) -> Dict[str, Any]:
        """输出沙箱开始初始化并保存"""
        event = self.present_sandbox_starting()
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
        model_id: str | None = None,
        model: str | None = None,
    ) -> Dict[str, Any]:
        """输出 Token 使用统计并保存"""
        event = self.present_token_usage(
            input_tokens,
            output_tokens,
            total_tokens,
            duration,
            model_id=model_id,
            model=model,
        )
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
