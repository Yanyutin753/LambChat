"""
DeepAgent 事件处理模块

处理 DeepAgent 的 astream_events 事件并转发到 Presenter。
"""

import json
import logging
import uuid
from io import StringIO
from typing import Any

from langchain_core.runnables.schema import CustomStreamEvent, StandardStreamEvent

from src.infra.writer.present import Presenter

logger = logging.getLogger(__name__)

# Type alias for astream_events event types
StreamEvent = StandardStreamEvent | CustomStreamEvent

# 预定义工具名常量
_TOOL_TASK = "task"

# 预定义错误指示器集合（使用 frozenset 加速成员检查）
_ERROR_INDICATORS = frozenset(
    ("error:", "validationerror", "failed", "error", "exception", "traceback")
)
_TOOL_ERROR_INDICATORS = frozenset(
    (
        "error:",
        "validationerror",
        "[mcp tool error]",
        "failed",
        "exception",
        "traceback",
    )
)


def _get_value(obj: Any, key: str, default: Any = 0) -> Any:
    """从 dict 或对象中获取值（模块级函数避免重复创建）"""
    return obj.get(key, default) if isinstance(obj, dict) else getattr(obj, key, default)


class AgentEventProcessor:
    """
    Agent 事件处理器

    处理 DeepAgent 的流式事件，跟踪子代理状态，并转发到 Presenter。
    使用 checkpoint_ns 追踪子代理嵌套层级。
    """

    __slots__ = (
        "presenter",
        "checkpoint_to_agent",
        "thinking_ids",
        "_output_buffer",
        "total_input_tokens",
        "total_output_tokens",
        "total_tokens",
        "total_cache_creation_tokens",
        "total_cache_read_tokens",
        "_debug_enabled",
        "_presenter_emit",
    )

    def __init__(self, presenter: Presenter):
        self.presenter = presenter
        self.checkpoint_to_agent: dict[str, tuple[str, str]] = {}
        self.thinking_ids: dict[str | None, str | None] = {}
        # 使用 StringIO 避免 O(n²) 字符串拼接
        self._output_buffer = StringIO()
        self.total_input_tokens = 0
        self.total_output_tokens = 0
        self.total_tokens = 0
        self.total_cache_creation_tokens = 0
        self.total_cache_read_tokens = 0
        # 缓存 presenter.emit 方法引用
        self._presenter_emit = presenter.emit

    @property
    def output_text(self) -> str:
        """获取累积的输出文本"""
        return self._output_buffer.getvalue()

    def _get_checkpoint_ns(self, metadata: dict[str, Any]) -> str:
        """从 metadata 中获取 checkpoint_ns"""
        return metadata.get("langgraph_checkpoint_ns") or metadata.get("checkpoint_ns", "")

    def _get_agent_context(self, checkpoint_ns: str) -> tuple[str | None, int]:
        """
        获取当前事件所属的子代理上下文

        Args:
            metadata: 事件元数据
            checkpoint_ns: 预提取的 checkpoint_ns

        Returns:
            (agent_id, depth) 元组，depth=0 表示主代理
        """
        if not checkpoint_ns or "|" not in checkpoint_ns:
            return None, 0

        # 使用 partition 避免完整分割
        first_segment, _, _ = checkpoint_ns.partition("|")

        agent_info = self.checkpoint_to_agent.get(first_segment)
        if agent_info:
            logger.debug(
                "Found subagent: segment=%s, agent_id=%s",
                first_segment[:30],
                agent_info[0],
            )
            return agent_info[0], 1

        logger.debug(
            "Subagent not found: segment=%s, known=%s",
            first_segment[:30],
            list(self.checkpoint_to_agent.keys())[:3],
        )
        return None, 1

    async def process_event(self, event: StreamEvent) -> None:
        """处理单个事件"""
        evt_type = event.get("event")
        tool_name = event.get("name", "")

        # 快速路径：task 工具特殊处理
        if tool_name == _TOOL_TASK:
            match evt_type:
                case "on_tool_start":
                    await self._handle_task_start(event)
                    return
                case "on_tool_end":
                    await self._handle_task_end(event)
                    return
                case "on_tool_error":
                    await self._handle_task_error(event)
                    return

        # 提取 checkpoint_ns（只提取一次）
        checkpoint_ns = self._get_checkpoint_ns(event.get("metadata", {}))
        current_agent_id, current_depth = self._get_agent_context(checkpoint_ns)

        # 调试日志
        if current_depth:
            logger.debug(
                "[Subagent] %s/%s: agent=%s, depth=%d, ns=%s",
                evt_type,
                tool_name or "N/A",
                current_agent_id,
                current_depth,
                checkpoint_ns[:60] if checkpoint_ns else "N/A",
            )

        # 使用 match 分发事件
        match evt_type:
            case "on_chat_model_end":
                self._handle_token_usage(event)
            case "on_chat_model_stream":
                await self._handle_chat_stream(event, current_agent_id, current_depth)
            case "on_tool_start":
                await self._handle_tool_start(event, tool_name, current_agent_id, current_depth)
            case "on_tool_end":
                await self._handle_tool_end(event, tool_name, current_agent_id, current_depth)

    async def _handle_task_start(self, event: StreamEvent) -> None:
        """处理 task 工具开始事件"""
        data = event.get("data", {})
        inp: dict[str, Any] = data.get("input", {})

        # 提取子代理信息
        subagent_type = inp.get("subagent_type", "unknown") if isinstance(inp, dict) else "unknown"
        description = inp.get("description", "")[:500] if isinstance(inp, dict) else ""
        run_id = event.get("run_id", uuid.uuid4().hex[:8])

        # 获取 checkpoint_ns
        metadata = event.get("metadata", {})
        checkpoint_ns = metadata.get("checkpoint_ns", "")

        # 生成 instance_id
        checkpoint_uuid = checkpoint_ns.rpartition(":")[2] if checkpoint_ns else run_id
        instance_id = f"{subagent_type}_{checkpoint_uuid[:8]}"

        # 计算深度
        if "|" in checkpoint_ns:
            first_seg, _, _ = checkpoint_ns.partition("|")
            current_depth = (
                2 if first_seg in self.checkpoint_to_agent else checkpoint_ns.count("|") + 1
            )
        else:
            current_depth = 1

        # 记录映射
        self.checkpoint_to_agent[checkpoint_ns] = (instance_id, subagent_type)

        logger.info(
            "[Subagent] Task started: id=%s, ns=%s, depth=%d, total=%d",
            instance_id,
            checkpoint_ns,
            current_depth,
            len(self.checkpoint_to_agent),
        )

        await self._presenter_emit(
            self.presenter.present_agent_call(
                agent_id=instance_id,
                agent_name=subagent_type,
                input_message=description,
                depth=current_depth,
            )
        )

    async def _handle_task_end(self, event: StreamEvent) -> None:
        """处理 task 工具结束事件"""
        data = event.get("data", {})
        out = data.get("output")
        result_text = str(out) if out is not None else ""

        # 提取结果文本
        out_update = getattr(out, "update", None) if out is not None else None
        if isinstance(out_update, dict):
            messages = out_update.get("messages", [])
            if messages:
                result_text = getattr(messages[0], "content", result_text)

        # 错误检测
        error_message = None
        if isinstance(out, dict):
            if out.get("error") or out.get("status") == "error":
                error_message = out.get("error") or out.get("message") or str(out)
        elif isinstance(out, str):
            out_lower = out.lower()
            if any(e in out_lower for e in _ERROR_INDICATORS):
                error_message = out

        # 获取 agent 信息
        metadata = event.get("metadata", {})
        checkpoint_ns = self._get_checkpoint_ns(metadata)
        agent_info = self.checkpoint_to_agent.pop(checkpoint_ns, None)

        if agent_info:
            current_instance_id, _ = agent_info
            current_depth = checkpoint_ns.count("|") + 1 if checkpoint_ns else 1
        else:
            current_instance_id, current_depth = "unknown", 1

        logger.debug(
            "Subagent ended: id=%s, depth=%d, error=%s",
            current_instance_id,
            current_depth,
            error_message is not None,
        )

        await self._presenter_emit(
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

        metadata = event.get("metadata", {})
        checkpoint_ns = self._get_checkpoint_ns(metadata)
        agent_info = self.checkpoint_to_agent.pop(checkpoint_ns, None)

        if agent_info:
            current_instance_id, _ = agent_info
            current_depth = checkpoint_ns.count("|") + 1 if checkpoint_ns else 1
        else:
            current_instance_id, current_depth = "unknown", 1

        logger.warning(
            "Subagent error: id=%s, depth=%d, error=%s",
            current_instance_id,
            current_depth,
            error_message[:200],
        )

        await self._presenter_emit(
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

        # 尝试获取 usage_metadata
        usage = getattr(response, "usage_metadata", None)
        if usage is None:
            metadata = getattr(response, "metadata", None)
            if metadata:
                usage = metadata.get("usage")

        if usage is None:
            return

        # 累加 token（内联 _add_tokens 逻辑）
        input_tok = _get_value(usage, "input_tokens")
        output_tok = _get_value(usage, "output_tokens")
        total_tok = _get_value(usage, "total_tokens")

        if isinstance(input_tok, int):
            self.total_input_tokens += input_tok
        if isinstance(output_tok, int):
            self.total_output_tokens += output_tok
        if isinstance(total_tok, int):
            self.total_tokens += total_tok

        # 缓存 token
        input_details = _get_value(usage, "input_token_details", {})
        if input_details:
            cache_creation = _get_value(input_details, "cache_creation")
            cache_read = _get_value(input_details, "cache_read")
            if isinstance(cache_creation, int):
                self.total_cache_creation_tokens += cache_creation
            if isinstance(cache_read, int):
                self.total_cache_read_tokens += cache_read

    async def _handle_chat_stream(
        self,
        event: StreamEvent,
        current_agent_id: str | None,
        current_depth: int,
    ) -> None:
        """处理聊天流式输出"""
        data = event["data"]
        chunk = data.get("chunk")
        if not chunk:
            return

        content = chunk.content
        chunk_id = chunk.id

        # 处理字符串内容
        if isinstance(content, str) and content:
            if current_depth == 0:
                self._output_buffer.write(content)
            await self._presenter_emit(
                self.presenter.present_text(
                    content,
                    depth=current_depth,
                    agent_id=current_agent_id,
                )
            )
            return

        # 处理列表内容（Anthropic 格式）
        if isinstance(content, list):
            present_thinking = self.presenter.present_thinking
            present_text = self.presenter.present_text
            emit = self._presenter_emit

            for block in content:
                if not isinstance(block, dict):
                    continue
                btype = block.get("type")
                if btype == "thinking":
                    thinking_text = block.get("thinking", "")
                    if thinking_text:
                        await emit(
                            present_thinking(
                                thinking_text,
                                thinking_id=chunk_id,
                                depth=current_depth,
                                agent_id=current_agent_id,
                            )
                        )
                elif btype == "text":
                    text = block.get("text", "")
                    if text:
                        self.thinking_ids[current_agent_id] = None
                        if current_depth == 0:
                            self._output_buffer.write(text)
                        await emit(
                            present_text(
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
        inp: dict[str, Any] = event.get("data", {}).get("input", {})
        tool_call_id = event.get("run_id") or f"tool_{uuid.uuid4().hex[:8]}"

        await self._presenter_emit(
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
        data = event.get("data", {})
        out = data.get("output", "")
        tool_call_id = event.get("run_id") or f"tool_{uuid.uuid4().hex[:8]}"

        # 提取 ToolMessage content（链式提取）
        raw = out
        # 使用 or 短路和链式 getattr 替代多次 hasattr
        raw = getattr(out, "content", None) if not isinstance(out, str) else out
        raw = getattr(raw, "content", raw) if not isinstance(raw, str) else raw

        # 转换为字符串
        if isinstance(raw, list):
            # 使用生成器表达式避免中间列表
            raw = "".join(p.get("text", "") if isinstance(p, dict) else str(p) for p in raw)
        elif not isinstance(raw, str):
            raw = str(raw)

        # 错误检测（使用字符串视图避免重复 lower() 调用）
        is_error, error_message = False, None
        if isinstance(raw, dict):
            if raw.get("error") or raw.get("status") == "error":
                is_error = True
                error_message = raw.get("error") or raw.get("message") or str(raw)
        elif isinstance(raw, str):
            raw_lower = raw.lower()
            # 使用 any 的短路特性
            if any(e in raw_lower for e in _TOOL_ERROR_INDICATORS):
                is_error, error_message = True, raw

        # JSON 解析（快速检查避免不必要的解析尝试）
        result: Any = raw
        if isinstance(raw, str) and raw and raw[0] in ("{", "["):
            try:
                parsed = json.loads(raw)
                if isinstance(parsed, dict):
                    result = parsed
            except (json.JSONDecodeError, TypeError):
                pass

        await self._presenter_emit(
            self.presenter.present_tool_result(
                tool_name,
                result if isinstance(result, dict) else str(result),
                tool_call_id=tool_call_id,
                success=not is_error,
                error=error_message,
                depth=current_depth,
                agent_id=current_agent_id,
            )
        )
