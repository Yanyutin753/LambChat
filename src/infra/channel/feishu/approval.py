"""Feishu human approval card handling."""

import json
from typing import Any

from src.infra.channel.feishu.manager import FeishuChannelManager
from src.infra.logging import get_logger

logger = get_logger(__name__)

EVENT_APPROVAL_REQUIRED = "approval_required"
FEISHU_APPROVAL_ACTION = "lambchat.approval"
_FEISHU_APPROVAL_ACTION_LOCK_TTL_SECONDS = 30
_feishu_approval_action_locks: set[str] = set()


def _approval_status_text(status: str) -> str:
    return {
        "pending": "等待确认",
        "processing": "正在处理",
        "approved": "已确认",
        "rejected": "已拒绝",
        "error": "处理失败",
    }.get(status, status)


def _approval_message_preview(message: str, *, max_chars: int = 1600) -> str:
    message = message.strip()
    if len(message) <= max_chars:
        return message
    return f"{message[:max_chars].rstrip()}\n\n...（内容较长，请打开详情页查看完整信息）"


def _coerce_json_dict(value: Any) -> dict[str, Any] | None:
    if isinstance(value, dict):
        return value
    if isinstance(value, str) and value.strip():
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return None
        return parsed if isinstance(parsed, dict) else None
    return None


def _extract_approval_result_status(result: Any) -> tuple[str | None, str]:
    data = _coerce_json_dict(result)
    if not data:
        return None, "pending"
    approval_id = data.get("approval_id")
    if not isinstance(approval_id, str) or not approval_id:
        return None, "pending"
    status = str(data.get("status") or "")
    if status == "approved" or data.get("approved") is True:
        return approval_id, "approved"
    if status == "rejected" or data.get("approved") is False:
        return approval_id, "rejected"
    if status == "timeout":
        return approval_id, "error"
    return approval_id, "pending"


def _approval_status_from_record(approval: Any, response: Any = None) -> str:
    status = str(getattr(approval, "status", "") or "")
    if status in {"approved", "rejected"}:
        return status
    approved = getattr(response, "approved", None)
    if approved is True:
        return "approved"
    if approved is False:
        return "rejected"
    return "error"


async def _get_existing_approval_status(approval_id: str) -> str:
    from src.infra.storage.mongodb import get_approval_storage

    storage = get_approval_storage()
    approval = await storage.get(approval_id)
    response = await storage.get_response(approval_id)
    return _approval_status_from_record(approval, response)


async def _respond_to_human_approval(approval_id: str, *, approved: bool) -> None:
    """以审批属主身份代答（飞书卡片点击在其自身信任域内完成授权）。"""
    from src.api.routes.human import resolve_approval_owner_id, respond_to_approval
    from src.infra.storage.mongodb import get_approval_storage
    from src.kernel.errors import AppError, ErrorCode
    from src.kernel.schemas.user import TokenPayload

    approval = await get_approval_storage().get(approval_id)
    owner_id = await resolve_approval_owner_id(approval) if approval is not None else None
    if not owner_id:
        raise AppError(ErrorCode.APPROVAL_NOT_FOUND)

    await respond_to_approval(
        approval_id,
        approved=approved,
        response="{}",
        user=TokenPayload(sub=owner_id, username="feishu-channel"),
    )


async def _claim_feishu_approval_action(approval_id: str) -> bool:
    if approval_id in _feishu_approval_action_locks:
        return False

    try:
        from src.infra.storage.redis import get_redis_client

        redis_client = get_redis_client()
        claimed = await redis_client.set(
            f"feishu:approval_action:{approval_id}",
            "1",
            nx=True,
            ex=_FEISHU_APPROVAL_ACTION_LOCK_TTL_SECONDS,
        )
        if not claimed:
            return False
    except Exception as e:
        logger.debug("[Feishu] Redis approval action dedupe unavailable: %s", e)

    _feishu_approval_action_locks.add(approval_id)
    return True


def _release_feishu_approval_action(approval_id: str) -> None:
    _feishu_approval_action_locks.discard(approval_id)


async def _build_approval_card_content(
    approval: dict[str, Any],
    *,
    session_url: str | None,
    status: str,
) -> str:
    approval_id = str(approval.get("id") or "")
    approval_type = str(approval.get("type") or "form")
    message = _approval_message_preview(str(approval.get("message") or "需要用户确认"))
    pending = status == "pending"

    elements: list[dict[str, Any]] = [
        {
            "tag": "markdown",
            "content": f"**需要用户确认**\n\n{message}",
        },
        {"tag": "hr"},
        {
            "tag": "markdown",
            "content": f"状态：**{_approval_status_text(status)}**",
        },
    ]

    actions: list[dict[str, Any]] = []
    if pending and approval_type == "confirm":
        actions.extend(
            [
                {
                    "tag": "button",
                    "text": {"tag": "plain_text", "content": "确认"},
                    "type": "primary",
                    "value": {
                        "action": FEISHU_APPROVAL_ACTION,
                        "approval_id": approval_id,
                        "approved": True,
                    },
                },
                {
                    "tag": "button",
                    "text": {"tag": "plain_text", "content": "拒绝"},
                    "type": "danger",
                    "value": {
                        "action": FEISHU_APPROVAL_ACTION,
                        "approval_id": approval_id,
                        "approved": False,
                    },
                },
            ]
        )

    if session_url:
        actions.append(
            {
                "tag": "button",
                "text": {"tag": "plain_text", "content": "打开详情页"},
                "type": "default",
                "url": session_url,
            }
        )

    if actions:
        elements.append({"tag": "action", "actions": actions})

    card = {"config": {"wide_screen_mode": True}, "elements": elements}
    return json.dumps(card, ensure_ascii=False)


def build_feishu_approval_processing_card_data(approval_id: str) -> dict[str, Any]:
    """Build card JSON returned synchronously to disable clicked approval buttons."""
    card: dict[str, Any] = {
        "config": {"wide_screen_mode": True},
        "elements": [
            {
                "tag": "markdown",
                "content": "**需要用户确认**\n\n已收到确认操作，正在处理审批请求。",
            },
            {"tag": "hr"},
            {
                "tag": "markdown",
                "content": f"状态：**{_approval_status_text('processing')}**",
            },
        ],
    }
    if approval_id:
        card["elements"].append(
            {
                "tag": "note",
                "elements": [
                    {
                        "tag": "plain_text",
                        "content": f"审批 ID：{approval_id}",
                    }
                ],
            }
        )
    return card


async def handle_feishu_approval_action(
    *,
    value: Any,
    message_id: str | None = None,
    user_id: str | None = None,
    instance_id: str | None = None,
    manager: FeishuChannelManager | None = None,
) -> bool:
    """Handle a Feishu card button click for LambChat approvals."""
    action_value = _coerce_json_dict(value)
    if not action_value or action_value.get("action") != FEISHU_APPROVAL_ACTION:
        return False

    approval_id = str(action_value.get("approval_id") or "")
    if not approval_id:
        return False
    approved = bool(action_value.get("approved"))
    logger.info(
        "[HITL] approval_id=%s Card action received approved=%s",
        approval_id,
        approved,
    )
    claimed = await _claim_feishu_approval_action(approval_id)
    if not claimed:
        status = await _get_existing_approval_status(approval_id)
        logger.info(
            "[HITL] approval_id=%s Action already in progress, refreshing card status=%s",
            approval_id,
            status,
        )
        if manager and user_id and message_id and status != "error":
            await _patch_feishu_approval_card(
                manager=manager,
                user_id=user_id,
                instance_id=instance_id,
                message_id=message_id,
                approval_id=approval_id,
                status=status,
            )
        return True

    try:
        from fastapi import HTTPException

        await _respond_to_human_approval(approval_id, approved=approved)
        status = "approved" if approved else "rejected"
        logger.info(
            "[HITL] approval_id=%s Approval action accepted status=%s",
            approval_id,
            status,
        )
    except HTTPException as e:
        if e.status_code == 400:
            status = await _get_existing_approval_status(approval_id)
            logger.info(
                "[HITL] approval_id=%s Approval action already handled status=%s",
                approval_id,
                status,
            )
        else:
            status = "error"
            logger.warning(
                "[HITL] approval_id=%s Failed to respond to approval from card action "
                "status_code=%s detail=%s",
                approval_id,
                e.status_code,
                e.detail,
            )
    except Exception as e:
        status = "error"
        logger.warning(
            "[HITL] approval_id=%s Failed to respond to approval from card action error=%s",
            approval_id,
            e,
        )

    if manager and user_id and message_id:
        await _patch_feishu_approval_card(
            manager=manager,
            user_id=user_id,
            instance_id=instance_id,
            message_id=message_id,
            approval_id=approval_id,
            status=status,
        )

    _release_feishu_approval_action(approval_id)

    return True


async def _patch_feishu_approval_card(
    *,
    manager: FeishuChannelManager,
    user_id: str,
    instance_id: str | None,
    message_id: str,
    approval_id: str,
    status: str,
) -> None:
    logger.info(
        "[HITL] approval_id=%s Patching clicked card to status=%s message_id=%s",
        approval_id,
        status,
        message_id,
    )
    try:
        client = manager._find_channel(user_id, instance_id)
        if client:
            content = await _build_approval_card_content(
                {
                    "id": approval_id,
                    "message": "审批请求已处理，任务将继续执行。",
                    "type": "confirm",
                },
                session_url=None,
                status=status,
            )
            await client.patch_card_message(message_id, content)
    except Exception as e:
        logger.debug(
            "[HITL] approval_id=%s Failed to patch clicked approval card: %s",
            approval_id,
            e,
        )
