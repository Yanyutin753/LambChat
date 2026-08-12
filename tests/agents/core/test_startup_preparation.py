from __future__ import annotations

import asyncio

import pytest

from src.agents.core.startup_preparation import PreparedAgentInputs, prepare_agent_inputs


@pytest.mark.asyncio
async def test_prepare_agent_inputs_starts_all_independent_work_together() -> None:
    release = asyncio.Event()
    started: set[str] = set()

    async def gated(name: str, value):
        started.add(name)
        await release.wait()
        return value

    task = asyncio.create_task(
        prepare_agent_inputs(
            model=gated("model", "llm"),
            backend=gated("backend", "backend"),
            skills_prompt=gated("skills", "skills"),
            tools=gated("tools", ["tool"]),
            checkpointer=gated("checkpointer", "checkpointer"),
        )
    )

    for _ in range(20):
        if len(started) == 5:
            break
        await asyncio.sleep(0)

    assert started == {"model", "backend", "skills", "tools", "checkpointer"}
    assert task.done() is False

    release.set()
    result = await task
    assert result == PreparedAgentInputs(
        model="llm",
        backend="backend",
        skills_prompt="skills",
        tools=["tool"],
        checkpointer="checkpointer",
    )


@pytest.mark.asyncio
async def test_prepare_agent_inputs_cancels_siblings_when_one_dependency_fails() -> None:
    cancelled = asyncio.Event()

    async def fail() -> str:
        raise RuntimeError("model unavailable")

    async def wait_until_cancelled():
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.set()

    with pytest.raises(ExceptionGroup) as exc_info:
        await prepare_agent_inputs(
            model=fail(),
            backend=wait_until_cancelled(),
            skills_prompt=wait_until_cancelled(),
            tools=wait_until_cancelled(),
            checkpointer=wait_until_cancelled(),
        )

    assert any(str(exc) == "model unavailable" for exc in exc_info.value.exceptions)
    assert cancelled.is_set() is True
