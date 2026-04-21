"""
Memory Infrastructure Module

Provides cross-session long-term memory capabilities with unified tool interface.
Uses the native MongoDB-backed backend.
"""

# Unified memory tools (auto-dispatch to active backend)
# Base abstractions (for adding new backends)
from src.infra.memory.client.base import (
    MemoryBackend,
    create_memory_backend,
    is_memory_enabled,
)
from src.infra.memory.tools import (
    get_all_memory_tools,
    get_memory_delete_tool,
    get_memory_recall_tool,
    get_memory_retain_tool,
)

__all__ = [
    # Unified tools (preferred API)
    "get_all_memory_tools",
    "get_memory_retain_tool",
    "get_memory_recall_tool",
    "get_memory_delete_tool",
    # Backend factory
    "create_memory_backend",
    "is_memory_enabled",
    "MemoryBackend",
]
