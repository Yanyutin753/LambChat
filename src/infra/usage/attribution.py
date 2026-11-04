"""Attribute detached costs without inheriting a graph, callbacks or execution guards."""

from contextlib import contextmanager
from contextvars import ContextVar

from src.infra.logging import get_logger

logger = get_logger(__name__)

_scope: ContextVar[tuple[str, str] | None] = ContextVar("usage_attribution", default=None)


@contextmanager
def usage_attribution(user_id: str, session_id: str):
    token = _scope.set((user_id, session_id))
    try:
        yield
    finally:
        _scope.reset(token)


def detached_usage_context(user_id: str | None) -> dict | None:
    scope = _scope.get()
    if scope is None:
        return None
    return {"session_id": scope[1], "run_id": None, "trace_id": None} if scope[0] == user_id else {}


async def session_usage_metadata(session_id: str, user_id: str | None = None) -> dict:
    if not session_id:
        return {}
    try:
        from bson import ObjectId

        from src.infra.session.storage import SessionStorage

        doc = await SessionStorage().collection.find_one(
            {"session_id": session_id},
            {"_id": 0, "metadata": 1, "user_id": 1},
        )
        if doc is None and ObjectId.is_valid(session_id):
            doc = await SessionStorage().collection.find_one(
                {"_id": ObjectId(session_id)}, {"metadata": 1, "user_id": 1}
            )
        if user_id and (doc or {}).get("user_id") != user_id:
            return {}
        metadata = (doc or {}).get("metadata") or {}
        return metadata if isinstance(metadata, dict) else {}
    except Exception as e:
        logger.debug("Failed to load session metadata for usage log %s: %s", session_id, e)
        return {}
