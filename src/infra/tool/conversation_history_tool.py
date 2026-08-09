"""Deferred internal tools for authorized conversation history access."""

from __future__ import annotations

import json
from typing import Annotated, Any

from langchain.tools import ToolRuntime, tool
from langchain_core.tools import BaseTool, InjectedToolArg
from pydantic import Field

from src.infra.async_utils import run_blocking_io
from src.infra.logging import get_logger
from src.infra.session.conversation_history import (
    ConversationHistoryInvalidArgumentError,
    ConversationHistoryNotFoundError,
    ConversationHistoryService,
)
from src.infra.tool.backend_utils import get_user_id_from_runtime

logger = get_logger(__name__)


async def _json_result(result: dict[str, Any]) -> str:
    return await run_blocking_io(json.dumps, result, ensure_ascii=False, default=str)


def _stable_error(error: Exception) -> str:
    if isinstance(error, ConversationHistoryInvalidArgumentError):
        return "invalid_argument"
    if isinstance(error, ConversationHistoryNotFoundError):
        return "not_found"
    return "temporarily_unavailable"


@tool
async def search_conversation_history(
    query: Annotated[str, "Text to find in historical user messages or final AI answers"],
    limit: Annotated[int, Field(ge=1, le=20, description="Page size, 1-20")] = 10,
    cursor: Annotated[str | None, "Opaque next_cursor from a prior result"] = None,
    runtime: Annotated[ToolRuntime, InjectedToolArg] = None,  # type: ignore[assignment]
) -> str:
    """Search the current user's visible conversation history and return run references."""
    user_id = get_user_id_from_runtime(runtime)
    if not user_id:
        return await _json_result({"success": False, "error": "not_authenticated"})
    try:
        return await _json_result(
            await ConversationHistoryService().search(
                user_id,
                query,
                limit=limit,
                cursor=cursor,
            )
        )
    except Exception as error:
        category = _stable_error(error)
        if category == "temporarily_unavailable":
            logger.warning(
                "Conversation history search failed: error_type=%s",
                type(error).__name__,
            )
        return await _json_result({"success": False, "error": category})


@tool
async def get_conversation_detail(
    session_id: Annotated[str, "Session ID returned by history search or memory recall"],
    run_id: Annotated[str | None, "Optional exact run ID"] = None,
    limit: Annotated[
        int,
        Field(ge=1, le=20, description="Session page size, 1-20; ignored for exact run"),
    ] = 10,
    cursor: Annotated[str | None, "Opaque next_cursor for session paging"] = None,
    runtime: Annotated[ToolRuntime, InjectedToolArg] = None,  # type: ignore[assignment]
) -> str:
    """Read final user/assistant turns from one authorized historical session."""
    user_id = get_user_id_from_runtime(runtime)
    if not user_id:
        return await _json_result({"success": False, "error": "not_authenticated"})
    try:
        return await _json_result(
            await ConversationHistoryService().get_detail(
                user_id,
                session_id,
                run_id=run_id,
                limit=limit,
                cursor=cursor,
            )
        )
    except Exception as error:
        category = _stable_error(error)
        if category == "temporarily_unavailable":
            logger.warning(
                "Conversation history detail failed: error_type=%s",
                type(error).__name__,
            )
        return await _json_result({"success": False, "error": category})


def get_conversation_history_tools() -> list[BaseTool]:
    return [search_conversation_history, get_conversation_detail]
