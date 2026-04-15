"""
Feishu 消息处理器模块

处理飞书消息的 Agent 执行和响应。
发送一条卡片消息，支持 markdown 渲染。
"""

import asyncio
import json
import sys
import time
from typing import Any, AsyncGenerator, Callable, Optional, cast

from src.infra.channel.feishu.channel import FeishuChannel
from src.infra.channel.feishu.manager import FeishuChannelManager
from src.infra.channel.feishu.markdown import FeishuMarkdownAdapter
from src.infra.logging import get_logger

logger = get_logger(__name__)

# Redis key prefix for Feishu chat session mapping
FEISHU_SESSION_KEY_PREFIX = "feishu:session:"

# 事件类型定义
EVENT_MESSAGE_CHUNK = "message:chunk"
EVENT_THINKING = "thinking"
EVENT_TOOL_START = "tool:start"
EVENT_TOOL_RESULT = "tool:result"
EVENT_DONE = "done"


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
        sender_id: str | None = None,
        chat_type: str | None = None,
    ):
        self.manager = manager
        self.user_id = user_id
        self.chat_id = chat_id
        self.reply_to_message_id = reply_to_message_id
        self.sender_id = sender_id
        self.chat_type = chat_type

        # 内容收集
        self.text_parts: list[str] = []
        self.tools_used: list[str] = []
        self.files_to_reveal: list[dict] = []

        # 处理中 emoji 控制
        self._processing_active = False
        self._processing_task: asyncio.Task | None = None

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

    async def start_processing_indicator(self, message_id: str) -> None:
        """启动处理中 emoji 循环指示器。"""
        self._processing_active = True
        self._processing_task = asyncio.create_task(self._processing_emoji_loop(message_id))

    async def stop_processing_indicator(self) -> None:
        """停止处理中 emoji 循环指示器。"""
        self._processing_active = False
        if self._processing_task and not self._processing_task.done():
            self._processing_task.cancel()
            try:
                await self._processing_task
            except asyncio.CancelledError:
                pass

    async def _processing_emoji_loop(self, message_id: str) -> None:
        """循环切换 emoji 表示正在处理。"""
        try:
            while self._processing_active:
                for emoji in FeishuChannel.PROCESSING_EMOJIS:
                    await asyncio.sleep(3)
                    if not self._processing_active:
                        break
                    await self.manager.add_reaction(self.user_id, message_id, emoji)
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.debug(f"[Feishu] Processing emoji error: {e}")

    async def _upload_image_from_uri(self, uri: str) -> str | None:
        """从 send:// URI 读取图片并上传到飞书，返回 image_key。"""
        from src.infra.storage.s3.service import get_or_init_storage

        base_client = self.manager._find_channel(self.user_id)
        if not base_client:
            return None
        client = cast(FeishuChannel, base_client)

        try:
            # send:// URI maps to S3 key path
            s3_key = uri.replace("send://", "")
            storage = await get_or_init_storage()
            backend = storage._get_backend()
            image_bytes = await backend.download(s3_key)
            if not image_bytes:
                return None
            return await client.upload_image(image_bytes)
        except Exception as e:
            logger.debug(f"[Feishu] Failed to upload image from URI {uri}: {e}")
            return None

    async def send_card_message(self) -> bool:
        """发送卡片消息（支持回复引用、图片嵌入）"""
        base_client = self.manager._find_channel(self.user_id)
        if not base_client:
            logger.warning(f"[Feishu] No client for user {self.user_id}")
            return False

        client = cast(FeishuChannel, base_client)
        content = await self._build_card_content_async(client)
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

    async def _build_card_content_async(self, client: "FeishuChannel") -> str:
        """构建飞书卡片消息内容（异步，支持图片上传嵌入）"""
        elements: list[dict[str, Any]] = []

        # ===== @mention（群聊回复时 @原发送者）=====
        if self.chat_type == "group" and self.sender_id:
            elements.append(
                {
                    "tag": "markdown",
                    "content": f'<at user_id="{self.sender_id}"></at>',
                }
            )

        # ===== 主要内容区域 =====
        if self.text_parts:
            raw_content = "".join(self.text_parts)
            # 使用带图片上传的适配器构建 elements
            elements.extend(
                await FeishuMarkdownAdapter.build_elements_with_images(
                    raw_content, self._upload_image_from_uri
                )
            )

        # ===== 元数据区域（工具 + 文件）=====
        metadata_parts = []

        if self.tools_used:
            unique_tools = list(dict.fromkeys(self.tools_used))
            tool_badges = " ".join(f"`{t}`" for t in unique_tools)
            metadata_parts.append(f"🔧 {tool_badges}")

        if self.files_to_reveal:
            file_names = [f.get("name", "未知文件") for f in self.files_to_reveal]
            metadata_parts.append(f"📎 {', '.join(file_names)}")

        if metadata_parts:
            elements.append({"tag": "hr"})
            elements.append({"tag": "markdown", "content": " · ".join(metadata_parts)})

        if not elements:
            elements.append({"tag": "div", "text": {"tag": "plain_text", "content": "(无内容)"}})

        card = {"config": {"wide_screen_mode": True}, "elements": elements}
        return json.dumps(card, ensure_ascii=False)

    async def upload_and_send_files(self) -> None:
        """上传文件并发送文件卡片

        直接从 S3 storage 读取文件内容，然后上传到飞书。
        """
        from src.infra.storage.s3.service import get_or_init_storage

        if not self.files_to_reveal:
            return

        base_client = self.manager._find_channel(self.user_id)
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
            sender_id_from_msg = metadata.get("sender_id")
            chat_type_from_msg = metadata.get("chat_type")
            attachments = metadata.get("attachments")

            # Resolve agent: use per-channel agent_id if configured, else global default
            agent_to_use = default_agent
            instance_id = metadata.get("instance_id")
            if instance_id:
                from src.infra.channel.channel_storage import ChannelStorage
                from src.kernel.schemas.channel import ChannelType

                ch_storage = ChannelStorage()
                ch_config = await ch_storage.get_config(user_id, ChannelType.FEISHU, instance_id)
                if ch_config and ch_config.get("agent_id"):
                    agent_to_use = ch_config["agent_id"]
                    logger.info(
                        f"[Feishu] Using channel agent: {agent_to_use} for instance {instance_id}"
                    )

            collector = FeishuResponseCollector(
                manager=manager,
                user_id=user_id,
                chat_id=chat_id,
                reply_to_message_id=original_message_id,
                sender_id=sender_id_from_msg,
                chat_type=chat_type_from_msg,
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
                agent_id=agent_to_use,
                message=content,
                user_id=user_id,
                executor=executor,
                attachments=attachments,
            )

            logger.info(f"[Feishu] Task submitted: session={session_id}, run_id={run_id}")

            # 启动处理中 emoji 指示器
            if original_message_id:
                await collector.start_processing_indicator(original_message_id)

            try:
                await _process_events(
                    collector=collector,
                    session_id=session_id,
                    run_id=run_id,
                    show_tools=show_tools,
                )
            finally:
                # 停止处理中 emoji 指示器
                await collector.stop_processing_indicator()

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
    from src.infra.channel.feishu import get_feishu_channel_manager, start_feishu_channels

    manager = get_feishu_channel_manager()
    handler = create_feishu_message_handler(
        manager=manager,
        default_agent=default_agent,
        show_tools=show_tools,
    )

    await start_feishu_channels(handler)
    logger.info("Feishu channels started")
