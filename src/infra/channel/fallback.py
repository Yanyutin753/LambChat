"""任务通知的渠道兜底投递（proactive 基础）。

用户不在线（WS 与 Web Push 均未送达）且任务终态（完成/失败）时，
把 agent 结果推到用户配置的渠道实例——Web 发起的长任务在手机 IM
上可回看，是主动推送闭环的兜底层。规则：

- 渠道发起的会话（session.metadata.channel_delivery 有值）不投——
  渠道 handler 已在 run 结束时即时回复，再投会重复；
- 投递目标取用户第一个「配置了 default_chat_id 的 enabled 渠道实例」
  （出站推送渠道与微信 iLink 均支持默认目标），零配置可用；
- 任何失败只记日志，不影响任务本身。
"""

from __future__ import annotations

from src.infra.logging import get_logger

logger = get_logger(__name__)

_FALLBACK_STATUSES = {"completed", "failed"}


async def deliver_task_fallback(
    *,
    user_id: str,
    session_id: str,
    run_id: str | None,
    status_value: str,
    message: str | None,
) -> bool:
    """用户离线时的渠道兜底投递；返回是否投递成功。"""
    if status_value not in _FALLBACK_STATUSES:
        return False
    try:
        # 渠道发起的会话由渠道 handler 即时回复，无需兜底
        from src.infra.session.manager import SessionManager

        session = await SessionManager().get_session(session_id)
        metadata = getattr(session, "metadata", None) if session else None
        if isinstance(metadata, dict) and metadata.get("channel_delivery"):
            return False

        target = await _resolve_fallback_target(user_id)
        if target is None:
            return False
        channel_type_value, instance_id, chat_id = target

        text = await _build_delivery_text(session_id, run_id, status_value, message)
        if not text:
            return False

        from src.infra.channel.manager import get_channel_coordinator
        from src.kernel.schemas.channel import ChannelType

        sent = await get_channel_coordinator().send_message(
            user_id,
            ChannelType(channel_type_value),
            chat_id,
            text,
            instance_id=instance_id,
        )
        if sent:
            logger.info(
                "Task fallback delivered via %s channel: user=%s session=%s",
                channel_type_value,
                user_id,
                session_id,
            )
        return sent
    except Exception as e:
        logger.warning(
            "Task channel fallback failed (user=%s session=%s): %s", user_id, session_id, e
        )
        return False


async def _resolve_fallback_target(user_id: str) -> tuple[str, str, str] | None:
    """用户第一个带 default_chat_id 的 enabled 渠道实例。"""
    from src.infra.channel.channel_storage import ChannelStorage

    configs = await ChannelStorage().list_user_configs(user_id)
    for config in configs:
        if not config.get("enabled", True):
            continue
        chat_id = str(config.get("default_chat_id") or "").strip()
        if not chat_id:
            continue
        channel_type = str(config.get("channel_type") or "")
        instance_id = str(config.get("instance_id") or "")
        if not channel_type:
            continue
        return channel_type, instance_id, chat_id
    return None


async def _build_delivery_text(
    session_id: str,
    run_id: str | None,
    status_value: str,
    message: str | None,
) -> str:
    """优先取 agent 实际输出文本，兜底用通知 message。"""
    if run_id:
        try:
            from src.infra.channel.delivery import extract_delivery_text
            from src.infra.session.trace_storage import get_trace_storage

            events = await get_trace_storage().get_run_events(session_id, run_id)
            text = extract_delivery_text(list(events))
            if text:
                prefix = "✅ 任务完成" if status_value == "completed" else "⚠️ 任务失败"
                return f"{prefix}\n\n{text}"
        except Exception as e:
            logger.debug("fallback text extraction failed: %s", e)
    if message:
        prefix = "✅ 任务完成" if status_value == "completed" else "⚠️ 任务失败"
        return f"{prefix}\n\n{message}"
    return ""
