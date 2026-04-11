"""
Memory Infrastructure Module

Provides cross-session long-term memory capabilities with unified tool interface.
Supports multiple backends: Hindsight and memU (cloud API).
Backend selection is controlled by MEMORY_PERFORM setting.
"""

# Unified memory tools (auto-dispatch to active backend)
# Base abstractions (for adding new backends)
from src.infra.memory.client.base import (
    MemoryBackend,
    create_memory_backend,
    is_memory_enabled,
)

# Backend-specific clients (for direct access if needed)
from src.infra.memory.client.hindsight import (
    close_all_hindsight_clients,
    close_hindsight_client,
    get_hindsight_client,
)
from src.infra.memory.client.memu import (
    close_memu_client,
    get_memu_client,
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
    # Backend clients (backward compat)
    "get_hindsight_client",
    "close_hindsight_client",
    "close_all_hindsight_clients",
    "get_memu_client",
    "close_memu_client",
]
