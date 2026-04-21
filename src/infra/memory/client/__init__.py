"""
Memory backend clients.

Each client implements the MemoryBackend interface from base.py.
Use create_memory_backend() factory to get the active backend.
"""

from src.infra.memory.client.base import (
    MemoryBackend,
    create_memory_backend,
    is_memory_enabled,
)
from src.infra.memory.client.native import NativeMemoryBackend

__all__ = [
    "MemoryBackend",
    "NativeMemoryBackend",
    "create_memory_backend",
    "is_memory_enabled",
]
