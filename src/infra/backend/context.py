"""Context variables for user isolation in backends."""

from contextvars import ContextVar
from typing import Optional

# Context variable for current user
current_user_id: ContextVar[Optional[str]] = ContextVar("current_user_id", default=None)

# Context variable for current session
current_session_id: ContextVar[Optional[str]] = ContextVar("current_session_id", default=None)


def set_user_context(user_id: str, session_id: Optional[str] = None) -> None:
    """Set user context for the current request.

    Args:
        user_id: The user identifier
        session_id: Optional session identifier
    """
    current_user_id.set(user_id)
    if session_id:
        current_session_id.set(session_id)


def get_user_id() -> str:
    """Get current user_id from context.

    Returns:
        The current user_id, or 'default' if not set
    """
    user_id = current_user_id.get()
    if not user_id:
        return "default"
    return user_id


def get_session_id() -> Optional[str]:
    """Get current session_id from context.

    Returns:
        The current session_id or None
    """
    return current_session_id.get()


def clear_user_context() -> None:
    """Clear user context (useful for testing)."""
    current_user_id.set(None)
    current_session_id.set(None)
