"""
DeepAgent 事件处理模块

处理 DeepAgent 的 astream_events 事件并转发到 Presenter。
"""

import base64
import json
import mimetypes
import uuid
from io import StringIO
from typing import Any

from langchain_core.runnables.schema import CustomStreamEvent, StandardStreamEvent

from src.infra.logging import get_logger
from src.infra.writer.present import Presenter

logger = get_logger(__name__)

# Type alias for astream_events event types
StreamEvent = StandardStreamEvent | CustomStreamEvent

# 预定义工具名常量
_TOOL_TASK = "task"

# 预定义错误指示器集合（使用 frozenset 加速成员检查）
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
        run_id = event.get("run_id", uuid.uuid4().hex)

        # 获取 checkpoint_ns
        metadata = event.get("metadata", {})
        checkpoint_ns = metadata.get("checkpoint_ns", "")

        # 生成 instance_id
        checkpoint_uuid = checkpoint_ns.rpartition(":")[2] if checkpoint_ns else run_id
        instance_id = f"{subagent_type}_{checkpoint_uuid}"

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

    def _resolve_agent_info(self, event: StreamEvent) -> tuple[str, int]:
        """从 task 事件中提取子代理信息并从映射中移除。

        Returns:
            (instance_id, depth)
        """
        checkpoint_ns = self._get_checkpoint_ns(event.get("metadata", {}))
        agent_info = self.checkpoint_to_agent.pop(checkpoint_ns, None)
        if agent_info:
            return agent_info[0], checkpoint_ns.count("|") + 1 if checkpoint_ns else 1
        return "unknown", 1

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

        # 错误检测：ToolMessage.status + 结构化字段，不做关键字扫描
        # （子代理结果内容不可控，关键字扫描容易误判）
        error_message = None
        tool_status = self._get_tool_status(out)
        if tool_status == "error":
            error_message = str(out) if out else "Tool execution failed"
        elif isinstance(out, dict):
            if out.get("error") or out.get("status") == "error":
                error_message = out.get("error") or out.get("message") or str(out)

        current_instance_id, current_depth = self._resolve_agent_info(event)

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

        current_instance_id, current_depth = self._resolve_agent_info(event)

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
                    text_id=chunk_id,
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
                                text_id=chunk_id,
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
        tool_call_id = event.get("run_id") or f"tool_{uuid.uuid4().hex}"

        # write_todos 工具：发送专用 todo 事件，跳过通用工具展示
        if tool_name == "write_todos":
            if isinstance(inp, dict):
                todos = inp.get("todos", [])
                if isinstance(todos, list) and todos:
                    await self._presenter_emit(
                        self.presenter.present_todo(
                            todos,
                            depth=current_depth,
                            agent_id=current_agent_id,
                        )
                    )
            return

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
        # write_todos 已在 _handle_tool_start 中处理，跳过
        if tool_name == "write_todos":
            return
        data = event.get("data", {})
        out = data.get("output", "")
        tool_call_id = event.get("run_id") or f"tool_{uuid.uuid4().hex}"

        # 提取工具结果内容，适配所有 LangGraph 工具输出类型
        # 支持的类型:
        #   1. str — 直接返回
        #   2. ToolMessage — 取 .content（str/list[dict]/None）
        #   3. list[ToolMessage] — 合并每个 .content
        #   4. list[dict] — 多模态内容 [{"type":"text","text":"..."}]
        #   5. dict {"content": ...} — 简单 dict 包装
        #   6. Command dict {"goto":[],"update":{"messages":[ToolMessage,...]}}
        #   7. Command 对象 — 有 .update 属性
        #   8. dict {"output": ...} — 嵌套输出
        #   9. 其他 dict — 保留结构化数据
        #  10. 其他对象 — str()
        raw = self._extract_tool_output(out)

        # 错误检测：优先使用 ToolMessage.status（框架权威信号），
        # 仅在无法获取 status 时 fallback 到内容关键字扫描
        is_error, error_message = self._detect_tool_error(out, raw)

        # JSON 解析（字符串可能是 JSON，尝试解析为结构化数据给前端）
        result: Any = raw
        if isinstance(raw, str) and raw and raw[0] in ("{", "["):
            try:
                parsed = json.loads(raw)
                if isinstance(parsed, dict):
                    result = parsed
                elif isinstance(parsed, list):
                    # MCP content blocks 嵌套数组，如 [[{"type":"text","text":"..."}], null]
                    normalized = AgentEventProcessor._normalize_content(parsed)
                    result = normalized if isinstance(normalized, dict) else str(normalized)
            except (json.JSONDecodeError, TypeError):
                pass

        # 将结果中的 base64 二进制数据上传到存储，替换为 URL
        if isinstance(result, dict) and "blocks" in result:
            await self._upload_binary_blocks(result)

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

    async def _upload_binary_blocks(self, result: dict) -> None:
        """将 result.blocks 中含 base64 的 block 上传到存储，用 URL 替换 base64。

        原地修改 result dict，无返回值。
        """
        blocks = result.get("blocks")
        if not isinstance(blocks, list):
            return

        has_binary = any(isinstance(b, dict) and b.get("base64") for b in blocks)
        if not has_binary:
            return

        try:
            from src.infra.storage.s3 import get_storage_service
            from src.infra.tool.reveal_file_tool import _ensure_storage_initialized

            await _ensure_storage_initialized()
            storage = get_storage_service()
        except Exception as e:
            logger.warning("Failed to initialize storage for binary upload: %s", e)
            return

        for block in blocks:
            if not isinstance(block, dict):
                continue
            b64_data = block.get("base64")
            if not b64_data or not isinstance(b64_data, str):
                continue

            try:
                raw_bytes = base64.b64decode(b64_data)
                mime_type = block.get("mime_type", "application/octet-stream")
                ext = mimetypes.guess_extension(mime_type) or ".bin"
                ext = ext.lstrip(".")
                filename = f"binary_{uuid.uuid4().hex[:8]}.{ext}"

                upload_result = await storage.upload_bytes(
                    data=raw_bytes,
                    folder="tool_binaries",
                    filename=filename,
                    content_type=mime_type,
                )

                proxy_url = f"/api/upload/file/{upload_result.key}"
                block.pop("base64", None)
                block["url"] = proxy_url
                logger.info(
                    "Uploaded binary block to storage: %s (%d bytes)",
                    upload_result.key,
                    len(raw_bytes),
                )
            except Exception as e:
                logger.warning("Failed to upload binary block: %s", e)

    # MCP media block 类型集合，用于快速判断
    _MCP_MEDIA_TYPES = frozenset(("image", "file"))
    _MCP_SKIP_KEYS = frozenset(("id",))

    @staticmethod
    def _extract_tool_output(out: Any) -> Any:
        """从 LangGraph 工具节点输出中提取可显示内容。

        支持所有 LangGraph + MCP 工具输出类型:
          1. str — 直接返回
          2. ToolMessage — 取 .content (优先 .artifact)
          3. list[BaseMessage] — 合并每个消息的 content
          4. Command 对象 — 取 .update.messages → 合并 content
          5. Command dict {"goto":[], "update":{"messages":[...]}}
          6. dict {"content": ...} / {"output": {"content": ...}}
          7. list[dict] — MCP 多模态 content blocks (text/image/file/resource)
          8. 其他 dict — 保留结构化数据
          9. 其他对象 — str()
        """
        if out is None:
            return ""
        if isinstance(out, str):
            return out

        # 1. 非 dict/list/str 对象: Command (.update) 或 BaseMessage (.content/.artifact)
        if not isinstance(out, (dict, list, str)):
            update = getattr(out, "update", None)
            if isinstance(update, dict):
                messages = update.get("messages")
                if messages:
                    return AgentEventProcessor._process_messages(messages)
                return update
            artifact = getattr(out, "artifact", None)
            if artifact is not None:
                return artifact
            content = getattr(out, "content", None)
            return AgentEventProcessor._normalize_content(content) if content is not None else ""

        # 3. list — [BaseMessage] 或 MCP content blocks [dict]
        if isinstance(out, list):
            if out and not isinstance(out[0], (dict, str)):
                return AgentEventProcessor._process_messages(out)
            return AgentEventProcessor._normalize_content(out)

        # 4. dict
        if isinstance(out, dict):
            update = out.get("update")
            if isinstance(update, dict):
                messages = update.get("messages")
                if messages:
                    return AgentEventProcessor._process_messages(messages)
                return update

            if "content" in out:
                return AgentEventProcessor._normalize_content(out["content"])

            nested = out.get("output")
            if nested is not None:
                if isinstance(nested, dict):
                    return AgentEventProcessor._normalize_content(nested.get("content", nested))
                return nested

            return out

    @staticmethod
    def _detect_tool_error(out: Any, raw: Any) -> tuple[bool, str | None]:
        """检测工具调用是否失败。

        检测优先级:
          1. ToolMessage.status == "error" — 框架权威信号（工具抛异常时设置）
          2. 结构化数据中的 error/status 字段
          3. 内容关键字扫描（仅当无法获取 ToolMessage.status 时作为 fallback）

        Args:
            out: 工具节点的原始输出（可能包含 ToolMessage 对象）
            raw: 经 _extract_tool_output 处理后的内容

        Returns:
            (is_error, error_message)
        """
        # 1. 从原始输出中提取 ToolMessage.status（最可靠）
        tool_status = AgentEventProcessor._get_tool_status(out)
        if tool_status == "error":
            return True, str(raw) if raw else "Tool execution failed"

        # 2. 结构化数据中的错误字段
        if isinstance(raw, dict):
            if raw.get("error") or raw.get("status") == "error":
                return True, raw.get("error") or raw.get("message") or str(raw)

        # 3. Fallback: 内容关键字扫描（仅在拿不到 ToolMessage.status 时）
        #    仅检查内容开头，避免文件/资源内容中包含 "Error:" 等关键字导致误判
        if isinstance(raw, str) and raw:
            first_line = raw.lstrip()[:200].lower()
            if any(first_line.startswith(e) for e in _TOOL_ERROR_INDICATORS):
                return True, raw

        return False, None

    @staticmethod
    def _get_tool_status(out: Any) -> str | None:
        """从工具原始输出中提取 ToolMessage.status。

        遍历各种包装类型（ToolMessage, list, Command, dict）找到 status 字段。
        """

        def _check(obj: Any) -> str | None:
            status = getattr(obj, "status", None)
            if status and isinstance(status, str):
                return status
            return None

        if out is None:
            return None

        # ToolMessage 或其他 BaseMessage 对象
        if not isinstance(out, (dict, list, str)):
            s = _check(out)
            if s:
                return s
            # Command 对象
            update = getattr(out, "update", None)
            if isinstance(update, dict):
                return AgentEventProcessor._get_tool_status(update.get("messages"))
            return None

        # list[BaseMessage] 或 MCP content blocks
        if isinstance(out, list):
            for item in out:
                if isinstance(item, (dict, str)):
                    continue
                s = _check(item)
                if s:
                    return s
            return None

        # dict — 检查嵌套 messages
        if isinstance(out, dict):
            update = out.get("update")
            if isinstance(update, dict):
                return AgentEventProcessor._get_tool_status(update.get("messages"))
            return None

        return None

    @staticmethod
    def _collect_blocks(
        content: list,
        text_parts: list[str],
        media_blocks: list[dict],
    ) -> bool:
        """遍历 content block 列表，将文本归入 text_parts、媒体归入 media_blocks。

        处理嵌套数组 (LangChain 双层包装)、非 dict 元素、
        MCP content block (text/image/file/resource) 等。

        Returns:
            是否包含媒体 block
        """
        _skip = AgentEventProcessor._MCP_SKIP_KEYS
        _media = AgentEventProcessor._MCP_MEDIA_TYPES
        has_media = False

        for block in content:
            # 嵌套数组 (LangChain 双层包装)：递归展平
            if isinstance(block, list):
                nested = AgentEventProcessor._normalize_content(block)
                if isinstance(nested, str):
                    text_parts.append(nested)
                elif isinstance(nested, dict):
                    if "text" in nested:
                        text_parts.append(nested["text"])
                    if "blocks" in nested:
                        media_blocks.extend(nested["blocks"])
                        has_media = True
                continue
            if not isinstance(block, dict):
                text_parts.append(str(block) if block is not None else "")
                continue

            btype = block.get("type", "")
            if btype == "text":
                text = block.get("text")
                text_parts.append(str(text) if text is not None else "")
            elif btype in _media:
                media_blocks.append(
                    {k: v for k, v in block.items() if k not in _skip} if "id" in block else block
                )
                has_media = True
            elif "text" in block:
                text_parts.append(str(block["text"]))
            else:
                media_blocks.append(
                    {k: v for k, v in block.items() if k not in _skip} if "id" in block else block
                )
                has_media = True

        return has_media

    @staticmethod
    def _normalize_content(content: Any) -> Any:
        """将 content 标准化为可显示格式。

        MCP content block 类型 (经 langchain-mcp-adapter 转换后):
          {"type": "text", "text": "..."}
          {"type": "image", "base64": "...", "mime_type": "..."}
          {"type": "image", "url": "...", "mime_type": "..."}
          {"type": "file", "url": "...", "mime_type": "..."}

        返回值策略:
          - 纯文本 (str 或仅 text blocks) → str
          - 包含 image/file → {"text": str, "blocks": list[dict]}
          - dict → dict
        """
        if isinstance(content, str):
            return content
        if isinstance(content, dict):
            return content
        if not isinstance(content, list):
            return str(content)

        text_parts: list[str] = []
        media_blocks: list[dict] = []
        AgentEventProcessor._collect_blocks(content, text_parts, media_blocks)

        if media_blocks:
            return {"text": "".join(text_parts), "blocks": media_blocks}

        text_result = "".join(text_parts)
        return text_result if text_result else content

    @staticmethod
    def _process_messages(messages: list) -> Any:
        """从消息列表中提取并合并所有 content。

        支持 BaseMessage 对象和 dict 格式的消息。
        保留 MCP 多模态 block 结构（image/file）。
        """
        text_parts: list[str] = []
        media_blocks: list[dict] = []
        has_media = False

        for msg in messages:
            # 提取 content 和 artifact
            if isinstance(msg, dict):
                content = msg.get("content", "")
                artifact = msg.get("artifact")
            else:
                content = getattr(msg, "content", "")
                artifact = getattr(msg, "artifact", None)

            # artifact 优先（结构化数据）
            if artifact is not None:
                text_parts.append(json.dumps(artifact, ensure_ascii=False))
                continue

            if isinstance(content, str):
                text_parts.append(content)
            elif isinstance(content, list):
                if AgentEventProcessor._collect_blocks(content, text_parts, media_blocks):
                    has_media = True
            elif isinstance(content, dict):
                text_parts.append(json.dumps(content, ensure_ascii=False))
            else:
                text_parts.append(str(content))

        text_result = "\n".join(text_parts)

        if has_media:
            return {"text": text_result, "blocks": media_blocks}

        return text_result
