"""
DeepAgent 事件处理模块

处理 DeepAgent 的 astream_events 事件并转发到 Presenter。
"""

import logging
import uuid
from typing import Any

from langchain_core.runnables.schema import CustomStreamEvent, StandardStreamEvent

from src.infra.writer.present import Presenter

logger = logging.getLogger(__name__)

# Type alias for astream_events event types
StreamEvent = StandardStreamEvent | CustomStreamEvent


class AgentEventProcessor:
    """
    Agent 事件处理器

    处理 DeepAgent 的流式事件，跟踪子代理状态，并转发到 Presenter。
    """

    def __init__(self, presenter: Presenter):
        self.presenter = presenter
        # 跟踪子代理（task工具）的执行状态
        # key: task_run_id, value: (instance_id, subagent_type, depth)
        self.task_run_id_to_agent: dict[str, tuple[str, str, int]] = {}
        # 跟踪每个 (depth, agent_id) 组合的 thinking 块 ID
        self.thinking_ids: dict[str, str | None] = {}
        # 收集输出文本
        self.output_text = ""
        # Token 统计
        self.total_input_tokens = 0
        self.total_output_tokens = 0
        self.total_tokens = 0

    def _get_current_agent_context(self, event: StreamEvent) -> tuple[str | None, int]:
        """
        获取当前事件所属的子代理上下文

        Args:
            event: 事件数据

        Returns:
            (agent_id, depth) 元组
        """
        parent_ids = event.get("parent_ids", [])

        for pid in parent_ids:
            if pid in self.task_run_id_to_agent:
                agent_info = self.task_run_id_to_agent[pid]
                return agent_info[0], agent_info[2]  # instance_id, depth

        return None, 0

    async def process_event(self, event: StreamEvent) -> None:
        """
        处理单个事件

        Args:
            event: astream_events 返回的事件
        """
        evt_type = event.get("event")
        tool_name = event.get("name", "")

        # 处理 task 工具开始
        if evt_type == "on_tool_start" and tool_name == "task":
            await self._handle_task_start(event)
            return

        # 处理 task 工具结束
        if evt_type == "on_tool_end" and tool_name == "task":
            await self._handle_task_end(event)
            return

        # 处理 task 工具错误
        if evt_type == "on_tool_error" and tool_name == "task":
            await self._handle_task_error(event)
            return

        # 获取当前子代理上下文
        current_agent_id, current_depth = self._get_current_agent_context(event)

        # 调试日志
        if current_depth > 0:
            parent_ids = event.get("parent_ids", [])
            logger.debug(
                "Event %s/%s: agent_id=%s, depth=%d, run_id=%s, parent_ids=%s",
                evt_type,
                tool_name or "N/A",
                current_agent_id,
                current_depth,
                event.get("run_id", "N/A"),
                parent_ids[:2] if parent_ids else [],
            )

        # 处理 token 统计
        if evt_type == "on_chat_model_end":
            self._handle_token_usage(event)
            return

        # 处理流式输出
        if evt_type == "on_chat_model_stream":
            await self._handle_chat_stream(event, current_agent_id, current_depth)
            return

        # 处理工具调用
        if evt_type == "on_tool_start":
            await self._handle_tool_start(event, tool_name, current_agent_id, current_depth)
            return

        if evt_type == "on_tool_end":
            await self._handle_tool_end(event, tool_name, current_agent_id, current_depth)
            return

    async def _handle_task_start(self, event: StreamEvent) -> None:
        """处理 task 工具开始事件"""
        inp: dict[str, Any] = event.get("data", {}).get("input", {})
        subagent_type = inp.get("subagent_type", "unknown") if isinstance(inp, dict) else "unknown"
        description = inp.get("description", "")[:500] if isinstance(inp, dict) else ""
        run_id = event.get("run_id", uuid.uuid4().hex[:8])
        instance_id = f"{subagent_type}_{run_id}"

        # 计算深度
        parent_ids = event.get("parent_ids", [])
        parent_depth = 0
        for pid in parent_ids:
            if pid in self.task_run_id_to_agent:
                parent_depth = self.task_run_id_to_agent[pid][2]
                break
        current_depth = parent_depth + 1

        # 记录映射
        self.task_run_id_to_agent[run_id] = (instance_id, subagent_type, current_depth)

        logger.debug(
            "Subagent started: instance_id=%s, run_id=%s, depth=%d",
            instance_id,
            run_id,
            current_depth,
        )

        await self.presenter.emit(
            self.presenter.present_agent_call(
                agent_id=instance_id,
                agent_name=subagent_type,
                input_message=description,
                depth=current_depth,
            )
        )

    async def _handle_task_end(self, event: StreamEvent) -> None:
        """处理 task 工具结束事件"""
        out = event.get("data", {}).get("output")
        result_text = str(out) if out is not None else ""

        if out is not None and hasattr(out, "update"):
            update_dict = out.update if isinstance(out.update, dict) else {}
            messages = update_dict.get("messages", [])
            if messages and hasattr(messages[0], "content"):
                result_text = messages[0].content

        # 检查输出中是否包含错误信息
        error_message = None
        if isinstance(out, dict):
            if out.get("error") or out.get("status") == "error":
                error_message = out.get("error") or out.get("message") or str(out)
        elif isinstance(out, str):
            error_indicators = [
                "Error:",
                "ValidationError",
                "failed",
                "error",
                "exception",
                "Traceback",
            ]
            if any(indicator.lower() in out.lower() for indicator in error_indicators):
                error_message = out

        run_id = event.get("run_id", "")
        agent_info = self.task_run_id_to_agent.get(run_id)

        if agent_info:
            current_instance_id, _, current_depth = agent_info
            del self.task_run_id_to_agent[run_id]
        else:
            current_instance_id = "unknown"
            current_depth = 1

        logger.debug(
            "Subagent ended: instance_id=%s, depth=%d, error=%s",
            current_instance_id,
            current_depth,
            error_message is not None,
        )

        await self.presenter.emit(
            self.presenter.present_agent_result(
                agent_id=current_instance_id,
                result=result_text,
                success=error_message is None,
                depth=current_depth,
                error=error_message,
            )
        )

    async def _handle_task_error(self, event: StreamEvent) -> None:
        """处理 task 工具错误事件"""
        error = event.get("data", {}).get("error")
        error_message = str(error) if error is not None else "Unknown error"

        run_id = event.get("run_id", "")
        agent_info = self.task_run_id_to_agent.get(run_id)

        if agent_info:
            current_instance_id, _, current_depth = agent_info
            del self.task_run_id_to_agent[run_id]
        else:
            current_instance_id = "unknown"
            current_depth = 1

        logger.warning(
            "Subagent error: instance_id=%s, depth=%d, error=%s",
            current_instance_id,
            current_depth,
            error_message[:200],
        )

        await self.presenter.emit(
            self.presenter.present_agent_result(
                agent_id=current_instance_id,
                result="",
                success=False,
                depth=current_depth,
                error=error_message,
            )
        )

    def _handle_token_usage(self, event: StreamEvent) -> None:
        """处理 token 使用统计"""
        response = event.get("data", {}).get("output")
        if not response:
            return

        usage = getattr(response, "usage_metadata", None)
        if usage:
            self._add_tokens(usage)
        else:
            metadata = getattr(response, "metadata", {})
            if metadata:
                usage = metadata.get("usage")
                if usage:
                    self._add_tokens(usage)

    def _add_tokens(self, usage: dict[str, Any]) -> None:
        """累加 token 统计"""
        input_tok = usage.get("input_tokens", 0)
        output_tok = usage.get("output_tokens", 0)
        total_tok = usage.get("total_tokens", 0)

        if isinstance(input_tok, int):
            self.total_input_tokens += input_tok
        if isinstance(output_tok, int):
            self.total_output_tokens += output_tok
        if isinstance(total_tok, int):
            self.total_tokens += total_tok

    async def _handle_chat_stream(
        self,
        event: StreamEvent,
        current_agent_id: str | None,
        current_depth: int,
    ) -> None:
        """处理聊天流式输出"""
        chunk = event["data"].get("chunk")
        if not chunk:
            return

        content = chunk.content
        id = chunk.id

        # 处理字符串内容
        if isinstance(content, str) and content:
            if current_depth == 0:
                self.output_text += content
            await self.presenter.emit(
                self.presenter.present_text(
                    content,
                    depth=current_depth,
                    agent_id=current_agent_id,
                )
            )

        # 处理列表内容（Anthropic 格式）
        elif isinstance(content, list):
            for block in content:
                btype = block.get("type", "") if isinstance(block, dict) else ""

                if btype == "thinking":
                    await self._handle_thinking_block(block, id, current_agent_id, current_depth)
                elif btype == "text":
                    await self._handle_text_block(block, current_agent_id, current_depth)

    async def _handle_thinking_block(
        self,
        block: dict[str, Any],
        id: str | None,
        current_agent_id: str | None,
        current_depth: int,
    ) -> None:
        """处理 thinking 块"""
        thinking_text = block.get("thinking", "")
        if not thinking_text:
            return

        await self.presenter.emit(
            self.presenter.present_thinking(
                thinking_text,
                thinking_id=id,
                depth=current_depth,
                agent_id=current_agent_id,
            )
        )

    async def _handle_text_block(
        self,
        block: dict[str, Any],
        current_agent_id: str | None,
        current_depth: int,
    ) -> None:
        """处理文本块"""
        text = block.get("text", "")
        if not text:
            return

        # 重置 thinking_id
        thinking_key = f"{current_depth}:{current_agent_id}"
        if self.thinking_ids.get(thinking_key):
            self.thinking_ids[thinking_key] = None

        if current_depth == 0:
            self.output_text += text

        await self.presenter.emit(
            self.presenter.present_text(
                text,
                depth=current_depth,
                agent_id=current_agent_id,
            )
        )

    async def _handle_tool_start(
        self,
        event: StreamEvent,
        tool_name: str,
        current_agent_id: str | None,
        current_depth: int,
    ) -> None:
        """处理工具调用开始"""
        inp: Any = event.get("data", {}).get("input", {})
        # 使用 run_id 作为 tool_call_id，保证 start/end 一致
        run_id = event.get("run_id", "")
        tool_call_id = run_id or f"tool_{uuid.uuid4().hex[:8]}"

        await self.presenter.emit(
            self.presenter.present_tool_start(
                tool_name,
                inp,
                tool_call_id=tool_call_id,
                depth=current_depth,
                agent_id=current_agent_id,
            )
        )

    async def _handle_tool_end(
        self,
        event: StreamEvent,
        tool_name: str,
        current_agent_id: str | None,
        current_depth: int,
    ) -> None:
        """处理工具调用结束"""
        out = event.get("data", {}).get("output", "")
        # 使用 run_id 作为 tool_call_id，保证与 start 一致
        run_id = event.get("run_id", "")
        tool_call_id = run_id or f"tool_{uuid.uuid4().hex[:8]}"

        # 检测是否是错误
        is_error = False
        error_message = None
        if isinstance(out, dict):
            # 检查是否有错误标记
            if out.get("error") or out.get("status") == "error":
                is_error = True
                error_message = out.get("error") or out.get("message") or str(out)
        elif isinstance(out, str):
            # 检测各种错误格式
            error_indicators = [
                "Error:",
                "ValidationError",
                "[MCP Tool Error]",
                "failed",
                "error",
                "exception",
                "Traceback",
            ]
            if any(indicator.lower() in out.lower() for indicator in error_indicators):
                is_error = True
                error_message = out

        await self.presenter.emit(
            self.presenter.present_tool_result(
                tool_name,
                str(out),
                tool_call_id=tool_call_id,
                success=not is_error,
                error=error_message,
                depth=current_depth,
                agent_id=current_agent_id,
            )
        )
