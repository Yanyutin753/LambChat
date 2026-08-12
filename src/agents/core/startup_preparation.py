"""Concurrency primitive for independent pre-model Agent dependencies."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable
from dataclasses import dataclass
from typing import Any, TypeVar

T = TypeVar("T")


async def _await_value(value: Awaitable[T]) -> T:
    return await value


@dataclass(frozen=True)
class PreparedAgentInputs:
    model: Any
    backend: Any
    skills_prompt: str
    tools: list[Any]
    checkpointer: Any


async def prepare_agent_inputs(
    *,
    model: Awaitable[Any],
    backend: Awaitable[Any],
    skills_prompt: Awaitable[str],
    tools: Awaitable[list[Any]],
    checkpointer: Awaitable[Any],
) -> PreparedAgentInputs:
    """Resolve independent startup inputs, cancelling siblings on failure."""
    async with asyncio.TaskGroup() as group:
        model_task: asyncio.Task[Any] = group.create_task(_await_value(model))
        backend_task: asyncio.Task[Any] = group.create_task(_await_value(backend))
        skills_task: asyncio.Task[str] = group.create_task(_await_value(skills_prompt))
        tools_task: asyncio.Task[list[Any]] = group.create_task(_await_value(tools))
        checkpointer_task: asyncio.Task[Any] = group.create_task(_await_value(checkpointer))

    return PreparedAgentInputs(
        model=model_task.result(),
        backend=backend_task.result(),
        skills_prompt=skills_task.result(),
        tools=tools_task.result(),
        checkpointer=checkpointer_task.result(),
    )
