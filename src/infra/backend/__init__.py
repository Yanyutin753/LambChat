"""Backend implementations for file operations."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .context import (
    clear_user_context,
    get_session_id,
    get_user_id,
    set_user_context,
)
from .deepagent import (
    create_memory_backend,
    create_persistent_backend,
    create_sandbox_backend,
)

if TYPE_CHECKING:
    from .skills_store import SkillsStoreBackend

__all__ = [
    # Context
    "set_user_context",
    "get_user_id",
    "get_session_id",
    "clear_user_context",
    # DeepAgent Backend
    "create_memory_backend",
    "create_persistent_backend",
    "create_sandbox_backend",
    # Skills Store Backend
    "SkillsStoreBackend",
    "create_skills_backend",
]


def __getattr__(name: str):
    if name in {"SkillsStoreBackend", "create_skills_backend"}:
        from .skills_store import SkillsStoreBackend, create_skills_backend

        return {
            "SkillsStoreBackend": SkillsStoreBackend,
            "create_skills_backend": create_skills_backend,
        }[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
