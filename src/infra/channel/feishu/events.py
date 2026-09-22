"""Feishu task event processing."""

import json
from typing import Any

from src.infra.async_utils import run_long_blocking_io
from src.infra.channel.feishu.approval import (
    EVENT_APPROVAL_REQUIRED,
    _extract_approval_result_status,
    _get_existing_approval_status,
)
from src.infra.channel.feishu.collector import FeishuResponseCollector
from src.infra.channel.feishu.handler_helpers import (
    EVENT_MESSAGE_CHUNK,
    EVENT_TOOL_RESULT,
    EVENT_TOOL_START,
    _extract_tool_media_files,
)
from src.infra.logging import get_logger

logger = get_logger(__name__)


async def _process_events(
    collector: FeishuResponseCollector,
    session_id: str,
    run_id: str,
    show_tools: bool,
) -> None:
    """处理事件流并收集响应"""
    from src.infra.session.dual_writer import get_dual_writer

    dual_writer = get_dual_writer()
    pending_approvals: dict[str, dict[str, Any]] = {}

    try:
        async for event in dual_writer.read_from_redis(session_id, run_id):
            event_type = event.get("event_type", "")
            data = event.get("data", {})

            if event_type == EVENT_MESSAGE_CHUNK:
                chunk = data.get("content", "")
                if chunk:
                    await collector.append_stream_chunk(chunk)

            elif event_type == EVENT_TOOL_START and show_tools:
                tool_name = data.get("tool", "")
                if tool_name:
                    collector.add_tool(tool_name)

            elif event_type == EVENT_APPROVAL_REQUIRED:
                approval_id = str(data.get("id") or "")
                logger.info(
                    "[HITL] approval_id=%s Received approval_required event",
                    approval_id,
                )
                if approval_id:
                    if collector.has_sent_approval_card(approval_id):
                        logger.info(
                            "[HITL] approval_id=%s Skip duplicate approval_required event",
                            approval_id,
                        )
                        continue
                    pending_approvals[approval_id] = data
                await collector.set_waiting_for_approval(data)
                sent = await collector.send_approval_card(data)
                if sent:
                    logger.info("[HITL] approval_id=%s Sent approval card", approval_id)
                else:
                    logger.warning(
                        "[HITL] approval_id=%s Failed to send approval card", approval_id
                    )

            elif event_type == EVENT_TOOL_RESULT:
                tool_name = data.get("tool", "")
                logger.debug(f"[Feishu] tool:result event: tool={tool_name}")
                result = data.get("result", "")
                result_approval_id, approval_status = _extract_approval_result_status(result)
                if result_approval_id:
                    # A tool result is only emitted after the approval was
                    # resolved (the tool already awaited the user response), so
                    # "pending" here means the tool forgot to carry its outcome.
                    # Never revert an already-handled card to pending — refresh
                    # the authoritative status from the approval record instead.
                    if approval_status == "pending":
                        approval_status = await _get_existing_approval_status(result_approval_id)
                    logger.info(
                        "[HITL] approval_id=%s Tool result received, finalizing card status=%s",
                        result_approval_id,
                        approval_status,
                    )
                    await collector.clear_waiting_for_approval()
                    approval = pending_approvals.get(result_approval_id) or {
                        "id": result_approval_id,
                        "message": "审批请求",
                        "type": "confirm",
                    }
                    await collector.update_approval_card(
                        result_approval_id,
                        approval,
                        status=approval_status,
                    )

                if tool_name == "reveal_file":
                    logger.info(f"[Feishu] reveal_file result type={type(result).__name__}")
                    if isinstance(result, str) and result:
                        try:
                            file_info = await run_long_blocking_io(json.loads, result)
                            if (
                                isinstance(file_info, dict)
                                and "key" in file_info
                                and "name" in file_info
                            ):
                                collector.add_file_to_reveal(file_info)
                                await collector.upload_and_send_files()
                                logger.info(
                                    f"[Feishu] Added file to reveal: {file_info.get('name')}"
                                )
                        except json.JSONDecodeError as e:
                            logger.warning(f"[Feishu] Failed to parse reveal_file result: {e}")
                    elif isinstance(result, dict):
                        if "key" in result and "name" in result:
                            collector.add_file_to_reveal(result)
                            await collector.upload_and_send_files()
                            logger.info(
                                f"[Feishu] Added file to reveal (dict): {result.get('name')}"
                            )

                for file_info in _extract_tool_media_files(result):
                    collector.add_file_to_reveal(file_info)
                    await collector.upload_and_send_files()
                    logger.info(
                        "[Feishu] Added tool media file to reveal: %s",
                        file_info.get("name"),
                    )

            elif event_type in ("done", "complete", "error"):
                break

        logger.info(f"[Feishu] Event processing completed for session={session_id}")

    except Exception as e:
        logger.error(f"[Feishu] Event processing error: {e}", exc_info=True)
