"""Cancellation-resistant helpers for session write recovery."""

import asyncio
from typing import TypeVar

ResultT = TypeVar("ResultT")


async def drain_task(task: asyncio.Task[ResultT]) -> ResultT:
    """Wait for a safety-critical task despite repeated cancellation of its waiter."""
    while not task.done():
        try:
            await asyncio.shield(task)
        except asyncio.CancelledError:
            continue
    return task.result()
