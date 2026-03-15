"""
Feishu 消息处理器模块

处理飞书消息的 Agent 执行和响应。
发送一条卡片消息，支持 markdown 渲染。
"""

import asyncio
import json
import logging
import re
import sys
import time
from typing import TYPE_CHECKING, Any, AsyncGenerator, Callable, Optional, cast

if TYPE_CHECKING:
    from src.infra.channel.feishu_channel import FeishuChannelManager

logger = logging.getLogger(__name__)

# Redis key prefix for Feishu chat session mapping
FEISHU_SESSION_KEY_PREFIX = "feishu:session:"


async def _get_feishu_session_id(chat_id: str) -> str:
    """获取飞书聊天对应的当前 session ID，如果不存在则创建默认的"""
    from src.infra.storage.redis import RedisStorage

    storage = RedisStorage()
    key = f"{FEISHU_SESSION_KEY_PREFIX}{chat_id}"
    session_id = await storage.get(key)

    if session_id is None:
        # 默认使用 chat_id 作为 session ID（兼容旧数据）
        session_id = f"feishu_{chat_id}"
        await storage.set(key, session_id)

    return session_id


async def _create_new_feishu_session(chat_id: str) -> str:
    """为飞书聊天创建新的 session ID"""
    from src.infra.storage.redis import RedisStorage

    storage = RedisStorage()
    key = f"{FEISHU_SESSION_KEY_PREFIX}{chat_id}"

    # 使用时间戳生成唯一的 session ID
    timestamp = int(time.time())
    session_id = f"feishu_{chat_id}_{timestamp}"

    # 存储到 Redis，不设置过期时间
    await storage.set(key, session_id)

    logger.info(f"[Feishu] Created new session for chat {chat_id}: {session_id}")
    return session_id


# ===== Markdown 适配工具 =====
class FeishuMarkdownAdapter:
    """
    将标准 Markdown 转换为飞书 lark_md 兼容格式

    飞书 lark_md 支持的语法:
    - **粗体** / *斜体*
    - `行内代码`
    - [链接](url)
    - 引用块 (> )
    - 有序/无序列表

    不支持:
    - ```代码块``` (需要用其他方式处理)
    - 标题 (#) (需要转换为粗体)
    - 表格
    """

    # 代码块占位符
    CODE_BLOCK_PLACEHOLDER = "\u0000CODE_BLOCK_{}\u0000"
    INLINE_CODE_PLACEHOLDER = "\u0000INLINE_CODE_{}\u0000"

    @classmethod
    def adapt(cls, text: str) -> str:
        """将 markdown 文本适配为飞书 lark_md 格式"""
        if not text:
            return text

        # 1. 保护代码块（先处理，避免被其他规则干扰）
        text, code_blocks = cls._extract_code_blocks(text)

        # 2. 保护行内代码
        text, inline_codes = cls._extract_inline_codes(text)

        # 3. 转换标题为粗体格式
        text = cls._convert_headers(text)

        # 4. 处理列表（确保正确的缩进和换行）
        text = cls._fix_lists(text)

        # 5. 处理引用块
        text = cls._fix_blockquotes(text)

        # 6. 优化段落间距
        text = cls._fix_paragraphs(text)

        # 7. 恢复行内代码
        text = cls._restore_inline_codes(text, inline_codes)

        # 8. 恢复代码块（转换为引用块样式）
        text = cls._restore_code_blocks(text, code_blocks)

        return text.strip()

    @classmethod
    def _extract_code_blocks(cls, text: str) -> tuple[str, dict]:
        """提取代码块，用占位符替换"""
        code_blocks = {}
        counter = [0]

        def replace_block(match: re.Match) -> str:
            lang = match.group(1) or ""
            code = match.group(2)
            idx = counter[0]
            counter[0] += 1
            code_blocks[idx] = (lang, code)
            return cls.CODE_BLOCK_PLACEHOLDER.format(idx)

        # 匹配 ```lang\ncode\n``` 格式
        pattern = r"```(\w*)\n(.*?)```"
        text = re.sub(pattern, replace_block, text, flags=re.DOTALL)

        return text, code_blocks

    @classmethod
    def _extract_inline_codes(cls, text: str) -> tuple[str, dict]:
        """提取行内代码，用占位符替换"""
        inline_codes = {}
        counter = [0]

        def replace_code(match: re.Match) -> str:
            code = match.group(1)
            idx = counter[0]
            counter[0] += 1
            inline_codes[idx] = code
            return cls.INLINE_CODE_PLACEHOLDER.format(idx)

        # 匹配 `code` 格式（非贪婪）
        text = re.sub(r"`([^`]+)`", replace_code, text)

        return text, inline_codes

    @classmethod
    def _convert_headers(cls, text: str) -> str:
        """将 markdown 标题转换为飞书兼容格式"""
        lines = text.split("\n")
        result = []

        for line in lines:
            # 匹配 # 标题格式
            header_match = re.match(r"^(#{1,6})\s+(.+)$", line)
            if header_match:
                content = header_match.group(2)
                # 转换为粗体 + 换行
                result.append(f"**{content}**")
                result.append("")  # 空行分隔
            else:
                result.append(line)

        return "\n".join(result)

    @classmethod
    def _fix_lists(cls, text: str) -> str:
        """修复列表格式"""
        lines = text.split("\n")
        result: list[str] = []
        in_list = False

        for line in lines:
            # 检测列表项
            is_list_item = bool(re.match(r"^(\s*)[-*+]\s+", line)) or bool(
                re.match(r"^(\s*)\d+\.\s+", line)
            )

            if is_list_item:
                # 确保列表项前有换行（如果不是连续列表）
                if not in_list and result and result[-1].strip():
                    result.append("")
                in_list = True
            else:
                if in_list and line.strip():
                    # 列表结束，添加空行
                    result.append("")
                in_list = False

            result.append(line)

        return "\n".join(result)

    @classmethod
    def _fix_blockquotes(cls, text: str) -> str:
        """修复引用块格式"""
        lines = text.split("\n")
        result = []

        for line in lines:
            # 确保引用块格式正确
            if line.startswith(">"):
                # 确保引用符号后有空格
                if len(line) > 1 and line[1] != " ":
                    line = "> " + line[1:]
            result.append(line)

        return "\n".join(result)

    @classmethod
    def _fix_paragraphs(cls, text: str) -> str:
        """优化段落间距"""
        # 移除多余的空行（超过2个连续换行）
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text

    @classmethod
    def _restore_inline_codes(cls, text: str, inline_codes: dict) -> str:
        """恢复行内代码"""
        for idx, code in inline_codes.items():
            placeholder = cls.INLINE_CODE_PLACEHOLDER.format(idx)
            # 转义特殊字符
            escaped_code = code.replace("\\", "\\\\").replace("`", "\\`")
            text = text.replace(placeholder, f"`{escaped_code}`")
        return text

    @classmethod
    def _restore_code_blocks(cls, text: str, code_blocks: dict) -> str:
        """恢复代码块（转换为引用块样式）"""
        for idx, (lang, code) in code_blocks.items():
            placeholder = cls.CODE_BLOCK_PLACEHOLDER.format(idx)

            # 转换为引用块样式
            code_lines = code.strip().split("\n")
            quoted_lines = [f"> `{line}`" for line in code_lines]

            # 添加语言标签（如果有）
            if lang:
                header = f"> **`{lang}`**"
                quoted_lines = [header] + quoted_lines

            # 添加前后空行
            block = "\n\n" + "\n".join(quoted_lines) + "\n\n"
            text = text.replace(placeholder, block)

        return text


# 事件类型定义
EVENT_MESSAGE_CHUNK = "message:chunk"
EVENT_THINKING = "thinking"
EVENT_TOOL_START = "tool:start"
EVENT_TOOL_RESULT = "tool:result"
EVENT_DONE = "done"


class FeishuResponseCollector:
    """
    飞书响应收集器

    收集 Agent 响应内容，发送一条美观的 markdown 卡片消息。
    """

    def __init__(
        self,
        manager: "FeishuChannelManager",
        user_id: str,
        chat_id: str,
        reply_to_message_id: str | None = None,
    ):
        self.manager = manager
        self.user_id = user_id
        self.chat_id = chat_id
        self.reply_to_message_id = reply_to_message_id

        # 内容收集
        self.text_parts: list[str] = []
        self.tools_used: list[str] = []
        self.files_to_reveal: list[dict] = []

    def append_text(self, chunk: str) -> None:
        """追加文本内容"""
        self.text_parts.append(chunk)

    def add_tool(self, tool_name: str) -> None:
        """添加使用的工具"""
        if tool_name:
            self.tools_used.append(tool_name)

    def add_file_to_reveal(self, file_info: dict) -> None:
        """添加待展示的文件"""
        self.files_to_reveal.append(file_info)

    def _build_card_content(self) -> str:
        """构建飞书卡片消息内容

        卡片结构:
        1. 主要内容（经过 markdown 适配）
        2. 分隔线
        3. 工具使用 + 文件信息（元数据区域）
        """
        elements = []

        # ===== 主要内容区域 =====
        if self.text_parts:
            raw_content = "".join(self.text_parts)
            # 使用 markdown 适配器处理内容
            adapted_content = FeishuMarkdownAdapter.adapt(raw_content)
            elements.append({"tag": "div", "text": {"tag": "lark_md", "content": adapted_content}})

        # ===== 元数据区域（工具 + 文件）=====
        metadata_parts = []

        # 工具使用
        if self.tools_used:
            unique_tools = list(dict.fromkeys(self.tools_used))
            tool_badges = " ".join(f"`{t}`" for t in unique_tools)
            metadata_parts.append(f"🔧 {tool_badges}")

        # 文件信息
        if self.files_to_reveal:
            file_names = [f.get("name", "未知文件") for f in self.files_to_reveal]
            metadata_parts.append(f"📎 {', '.join(file_names)}")

        # 如果有元数据，添加分隔线和元数据
        if metadata_parts:
            elements.append({"tag": "hr"})
            elements.append(
                {"tag": "div", "text": {"tag": "lark_md", "content": " · ".join(metadata_parts)}}
            )

        # 如果没有任何内容
        if not elements:
            elements.append({"tag": "div", "text": {"tag": "plain_text", "content": "(无内容)"}})

        # 构建卡片
        card = {"config": {"wide_screen_mode": True}, "elements": elements}

        return json.dumps(card, ensure_ascii=False)

    async def send_card_message(self) -> bool:
        """发送卡片消息（支持回复引用）"""
        from src.infra.channel.feishu_channel import FeishuChannel

        content = self._build_card_content()
        base_client = self.manager._channels.get(self.user_id)
        if not base_client:
            logger.warning(f"[Feishu] No client for user {self.user_id}")
            return False

        client = cast(FeishuChannel, base_client)
        success = await client.send_card_message(
            self.chat_id, content, reply_to_id=self.reply_to_message_id
        )
        if success:
            reply_info = (
                f" (reply to {self.reply_to_message_id})" if self.reply_to_message_id else ""
            )
            logger.info(f"[Feishu] Card message sent to {self.chat_id}{reply_info}")
        else:
            logger.warning("[Feishu] Failed to send card message")
        return success

    async def upload_and_send_files(self) -> None:
        """上传文件并发送文件卡片

        直接从 S3 storage 读取文件内容，然后上传到飞书。
        """
        from src.api.routes.upload import get_or_init_storage
        from src.infra.channel.feishu_channel import FeishuChannel

        if not self.files_to_reveal:
            return

        base_client = self.manager._channels.get(self.user_id)
        if not base_client:
            logger.warning(f"[Feishu] No client for user {self.user_id}")
            return

        client = cast(FeishuChannel, base_client)

        try:
            storage = await get_or_init_storage()
        except Exception as e:
            logger.error(f"[Feishu] Failed to init storage: {e}")
            return

        for file_info in self.files_to_reveal:
            try:
                file_name = file_info.get("name", "unknown")
                file_key = file_info.get("key", "")

                if not file_key:
                    logger.warning(f"[Feishu] No key for file {file_name}")
                    continue

                logger.info(f"[Feishu] Reading file {file_name} from storage, key={file_key}")

                backend = storage._get_backend()
                file_data = await backend.download(file_key)
                if not file_data:
                    logger.warning(f"[Feishu] File not found or empty: {file_key}")
                    continue

                logger.info(f"[Feishu] Read file {file_name}, size: {len(file_data)} bytes")

                feishu_file_key = await client.upload_bytes(
                    file_data=file_data,
                    file_name=file_name,
                )
                if feishu_file_key:
                    await client.send_file_by_key(
                        chat_id=self.chat_id,
                        file_key=feishu_file_key,
                        file_name=file_name,
                    )
                    logger.info(f"[Feishu] Sent file: {file_name}")
                else:
                    logger.warning(f"[Feishu] Failed to upload file {file_name} to Feishu")
            except Exception as e:
                logger.error(f"[Feishu] Failed to upload file {file_info.get('name')}: {e}")


async def execute_feishu_agent(
    session_id: str,
    agent_id: str,
    message: str,
    user_id: str,
    presenter: Optional[Any] = None,
    disabled_tools: list[str] | None = None,
    agent_options: dict | None = None,
    attachments: list[dict] | None = None,
) -> AsyncGenerator[dict[str, Any], None]:
    """执行 Agent 并生成事件流"""
    from src.agents.core.base import AgentFactory
    from src.infra.task.exceptions import TaskInterruptedError

    agent = await AgentFactory.get(agent_id)
    run_id = presenter.run_id if presenter else None

    try:
        async for event in agent.stream(
            message,
            session_id,
            user_id=user_id,
            presenter=presenter,
            disabled_tools=disabled_tools,
            agent_options=agent_options,
            attachments=attachments,
        ):
            yield event
    except (asyncio.CancelledError, TaskInterruptedError):
        if run_id:
            await agent.close(run_id)
        raise


def create_feishu_message_handler(
    manager: "FeishuChannelManager",
    default_agent: str,
    show_tools: bool = True,
) -> Callable:
    """
    创建飞书消息处理器

    Args:
        manager: 飞书渠道管理器
        default_agent: 默认 Agent ID
        show_tools: 是否显示工具调用
    """
    from src.infra.task.manager import get_task_manager

    async def feishu_message_handler(
        user_id: str,
        sender_id: str,
        chat_id: str,
        content: str,
        metadata: dict,
    ) -> None:
        """处理飞书消息"""
        print(
            f"[DEBUG] feishu_message_handler: {content[:50]}",
            file=sys.stderr,
            flush=True,
        )

        try:
            logger.info(
                f"[Feishu] Processing message from {sender_id} for user {user_id}: {content[:50]}..."
            )

            # 处理 /new 命令 - 严格匹配
            if content.strip() == "/new":
                new_session_id = await _create_new_feishu_session(chat_id)
                await manager.send_message(user_id, chat_id, "✅ 已创建新对话，请发送消息开始")
                logger.info(f"[Feishu] New session created for chat {chat_id}: {new_session_id}")
                return

            # 获取当前 session ID
            session_id = await _get_feishu_session_id(chat_id)
            task_manager = get_task_manager()

            original_message_id = metadata.get("message_id")

            collector = FeishuResponseCollector(
                manager=manager,
                user_id=user_id,
                chat_id=chat_id,
                reply_to_message_id=original_message_id,
            )

            async def executor(
                session_id: str,
                agent_id: str,
                message: str,
                user_id: str,
                presenter=None,
                disabled_tools=None,
                agent_options=None,
                attachments=None,
            ):
                async for event in execute_feishu_agent(
                    session_id=session_id,
                    agent_id=agent_id,
                    message=message,
                    user_id=user_id,
                    presenter=presenter,
                    disabled_tools=disabled_tools,
                    agent_options=agent_options,
                    attachments=attachments,
                ):
                    yield event

            run_id, _ = await task_manager.submit(
                session_id=session_id,
                agent_id=default_agent,
                message=content,
                user_id=user_id,
                executor=executor,
            )

            logger.info(f"[Feishu] Task submitted: session={session_id}, run_id={run_id}")

            await _process_events(
                collector=collector,
                session_id=session_id,
                run_id=run_id,
                show_tools=show_tools,
            )

            await collector.send_card_message()
            await collector.upload_and_send_files()

            logger.info(f"[Feishu] Message processing completed for {chat_id}")

        except Exception as e:
            logger.error(f"[Feishu] Error handling message: {e}", exc_info=True)
            try:
                await manager.send_message(
                    user_id, chat_id, f"❌ 处理消息时发生错误: {str(e)[:200]}"
                )
            except Exception:
                pass

    return feishu_message_handler


async def _process_events(
    collector: FeishuResponseCollector,
    session_id: str,
    run_id: str,
    show_tools: bool,
) -> None:
    """处理事件流并收集响应"""
    from src.infra.session.dual_writer import get_dual_writer

    dual_writer = get_dual_writer()

    try:
        async for event in dual_writer.read_from_redis(session_id, run_id):
            event_type = event.get("event_type", "")
            data = event.get("data", {})

            if event_type == EVENT_MESSAGE_CHUNK:
                chunk = data.get("content", "")
                if chunk:
                    collector.append_text(chunk)

            elif event_type == EVENT_TOOL_START and show_tools:
                tool_name = data.get("tool", "")
                if tool_name:
                    collector.add_tool(tool_name)

            elif event_type == EVENT_TOOL_RESULT:
                tool_name = data.get("tool", "")
                logger.debug(f"[Feishu] tool:result event: tool={tool_name}")
                if tool_name == "reveal_file":
                    result = data.get("result", "")
                    logger.info(f"[Feishu] reveal_file result type={type(result).__name__}")
                    if isinstance(result, str) and result:
                        try:
                            file_info = json.loads(result)
                            if (
                                isinstance(file_info, dict)
                                and "key" in file_info
                                and "name" in file_info
                            ):
                                collector.add_file_to_reveal(file_info)
                                logger.info(
                                    f"[Feishu] Added file to reveal: {file_info.get('name')}"
                                )
                        except json.JSONDecodeError as e:
                            logger.warning(f"[Feishu] Failed to parse reveal_file result: {e}")
                    elif isinstance(result, dict):
                        if "key" in result and "name" in result:
                            collector.add_file_to_reveal(result)
                            logger.info(
                                f"[Feishu] Added file to reveal (dict): {result.get('name')}"
                            )

            elif event_type in ("done", "complete", "error"):
                break

        logger.info(f"[Feishu] Event processing completed for session={session_id}")

    except Exception as e:
        logger.error(f"[Feishu] Event processing error: {e}", exc_info=True)


async def setup_feishu_handler(
    default_agent: str,
    show_tools: bool = True,
) -> None:
    """
    设置飞书消息处理器

    Args:
        default_agent: 默认 Agent ID
        show_tools: 是否显示工具调用
    """
    from src.infra.channel.feishu_channel import (
        get_feishu_channel_manager,
        start_feishu_channels,
    )

    manager = get_feishu_channel_manager()
    handler = create_feishu_message_handler(
        manager=manager,
        default_agent=default_agent,
        show_tools=show_tools,
    )

    await start_feishu_channels(handler)
    logger.info("Feishu channels started")
