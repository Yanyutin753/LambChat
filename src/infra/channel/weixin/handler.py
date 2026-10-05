"""微信消息处理：入站消息 → agent 执行 → 纯文本回复。

微信 iLink 是纯文本通道（无卡片/流式概念），回复一次性发送：
message:chunk 拼接为完整文本，approval_required 以文本提示兜底
（完整审批交互去 Web UI），工具调用过程静默。
"""

from __future__ import annotations

import time
from typing import Any, AsyncGenerator, Callable

from src.infra.logging import get_logger

logger = get_logger(__name__)

WEIXIN_SESSION_KEY_PREFIX = "weixin:session:"
EVENT_MESSAGE_CHUNK = "message:chunk"
EVENT_APPROVAL_REQUIRED = "approval_required"

APPROVAL_HINT = "⏸️ 这一步需要人工确认，请到 LambChat 网页端处理后再继续。"
MAX_REPLY_CHARS = 3500  # 微信单条消息安全上限内留余量


async def _get_weixin_session_id(chat_id: str) -> str:
    from src.infra.storage.redis import RedisStorage

    storage = RedisStorage()
    key = f"{WEIXIN_SESSION_KEY_PREFIX}{chat_id}"
    session_id = await storage.get(key)
    if session_id is None:
        session_id = f"weixin_{chat_id}"
        await storage.set(key, session_id)
    return session_id


async def _create_new_weixin_session(chat_id: str) -> str:
    from src.infra.storage.redis import RedisStorage

    storage = RedisStorage()
    session_id = f"weixin_{chat_id}_{int(time.time())}"
    await storage.set(f"{WEIXIN_SESSION_KEY_PREFIX}{chat_id}", session_id)
    return session_id


async def execute_weixin_agent(
    session_id: str,
    agent_id: str,
    message: str,
    user_id: str,
    presenter: Any = None,
    agent_options: dict | None = None,
    persona_system_prompt: str | None = None,
    enabled_skills: list[str] | None = None,
) -> AsyncGenerator[dict[str, Any], None]:
    """执行 Agent 并透传事件流（与 feishu execute 同构）。"""
    from src.agents.core.base import AgentFactory

    agent = await AgentFactory.get(agent_id)
    async for event in agent.stream(
        message,
        session_id,
        user_id=user_id,
        presenter=presenter,
        agent_options=agent_options,
        persona_system_prompt=persona_system_prompt,
        enabled_skills=enabled_skills,
    ):
        yield event


async def _process_events_and_reply(
    send: Callable[[str], Any],
    session_id: str,
    run_id: str,
) -> None:
    """消费 run 事件流：拼 chunk 文本，结束时一次性回复。"""
    from src.infra.session.dual_writer import get_dual_writer

    chunks: list[str] = []
    try:
        async for event in get_dual_writer().read_from_redis(session_id, run_id):
            event_type = event.get("event_type", "")
            data = event.get("data", {})
            if event_type == EVENT_MESSAGE_CHUNK:
                chunk = data.get("content", "")
                if chunk:
                    chunks.append(chunk)
            elif event_type == EVENT_APPROVAL_REQUIRED:
                await send(APPROVAL_HINT)
            elif event_type in ("done", "complete", "error"):
                if event_type == "error":
                    error_message = str(data.get("message") or data.get("error") or "")
                    if error_message:
                        await send(f"⚠️ 执行出错：{error_message[:500]}")
                break
    except Exception as e:
        logger.error("[Weixin] event processing error: %s", e, exc_info=True)
        if chunks:
            await send("".join(chunks)[:MAX_REPLY_CHARS])
        return

    text = "".join(chunks).strip()
    if text:
        await send(text[:MAX_REPLY_CHARS])
    else:
        logger.debug("[Weixin] run %s produced no reply text", run_id)


def create_weixin_message_handler(
    manager: Any,
    default_agent: str,
) -> Callable:
    """创建微信消息处理器（对齐 feishu handler 模式）。"""

    async def weixin_message_handler(
        user_id: str,
        sender_id: str,
        chat_id: str,
        content: str,
        metadata: dict,
    ) -> None:
        from src.infra.task.manager import get_task_manager

        instance_id = metadata.get("instance_id")
        context_token = metadata.get("context_token")

        async def send(text: str) -> None:
            await manager.send_message(user_id, chat_id, text, instance_id, context_token)

        try:
            if content.strip() == "/new":
                session_id = await _create_new_weixin_session(chat_id)
                await send(f"✅ 已创建新对话 {session_id}，请发送消息开始")
                return

            session_id = await _get_weixin_session_id(chat_id)
            task_manager = get_task_manager()

            # 渠道实例级配置（agent/model/persona/project）
            agent_to_use = default_agent
            model_id: str | None = None
            project_id: str | None = None
            persona_preset_id: str | None = None
            agent_options: dict[str, Any] | None = None
            if instance_id:
                from src.infra.channel.channel_storage import ChannelStorage
                from src.kernel.schemas.channel import ChannelType

                ch_config = await ChannelStorage().get_config(
                    user_id, ChannelType.WEIXIN, instance_id
                )
                if ch_config:
                    agent_to_use = ch_config.get("agent_id") or agent_to_use
                    model_id = ch_config.get("model_id")
                    project_id = ch_config.get("project_id")
                    persona_preset_id = ch_config.get("persona_preset_id")

            persona_system_prompt: str | None = None
            enabled_skills: list[str] | None = None
            if persona_preset_id:
                try:
                    from src.infra.persona_preset.manager import PersonaPresetManager

                    snapshot = await PersonaPresetManager().use_preset(
                        persona_preset_id, user_id=user_id, is_admin=False
                    )
                    persona_system_prompt = snapshot.system_prompt
                    enabled_skills = snapshot.skill_names or None
                except Exception as e:
                    logger.warning(
                        "[Weixin] ignore unavailable persona %s: %s", persona_preset_id, e
                    )

            if model_id:
                agent_options = {**(agent_options or {}), "model_id": model_id}

            async def executor(
                session_id: str,
                agent_id: str,
                message: str,
                user_id: str,
                presenter=None,
                disabled_tools=None,
                agent_options=None,
                attachments=None,
                disabled_skills=None,
                enabled_skills=None,
                persona_system_prompt=None,
                disabled_mcp_tools=None,
                recommendation_input=None,
                team_id=None,
                active_goal=None,
                auto_mode=False,
            ):
                async for event in execute_weixin_agent(
                    session_id=session_id,
                    agent_id=agent_id,
                    message=message,
                    user_id=user_id,
                    presenter=presenter,
                    agent_options=agent_options,
                    persona_system_prompt=persona_system_prompt,
                    enabled_skills=enabled_skills,
                ):
                    yield event

            run_id, _ = await task_manager.submit(
                session_id=session_id,
                agent_id=agent_to_use,
                message=content,
                user_id=user_id,
                executor=executor,
                agent_options=agent_options,
                project_id=project_id,
                enabled_skills=enabled_skills,
                persona_system_prompt=persona_system_prompt,
                auto_mode=True,
            )

            # 会话级渠道投递元数据：任务完成通知/后续 proactive 推送复用
            try:
                from src.infra.session.manager import SessionManager
                from src.kernel.schemas.channel import ChannelType

                await SessionManager().update_session_metadata(
                    session_id,
                    {
                        "channel_delivery": {
                            "channel_type": ChannelType.WEIXIN.value,
                            "chat_id": chat_id,
                            "channel_instance_id": instance_id,
                            "enabled": True,
                            "send_on_success": True,
                        }
                    },
                )
            except Exception as e:
                logger.debug("[Weixin] failed to tag channel_delivery: %s", e)

            await _process_events_and_reply(send, session_id, run_id)
        except Exception as e:
            logger.error("[Weixin] message handling failed: %s", e, exc_info=True)
            try:
                await send(f"⚠️ 处理消息时出错：{e}")
            except Exception:
                pass

    return weixin_message_handler
