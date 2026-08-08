from src.agents.fast_agent.context import FastAgentContext
from src.agents.search_agent.context import SearchAgentContext


class _CloseableSandbox:
    def __init__(self) -> None:
        self.close_calls = 0

    async def aclose(self) -> None:
        self.close_calls += 1


def test_fast_agent_context_generates_fresh_default_session_id_per_instance() -> None:
    first = FastAgentContext()
    second = FastAgentContext()

    assert first.session_id != second.session_id


def test_search_agent_context_generates_fresh_default_session_id_per_instance() -> None:
    first = SearchAgentContext()
    second = SearchAgentContext()

    assert first.session_id != second.session_id


async def test_search_agent_context_closes_run_sandbox_once_and_clears_reference() -> None:
    context = SearchAgentContext()
    sandbox = _CloseableSandbox()

    context.set_run_sandbox(sandbox)
    await context.close()
    await context.close()

    assert sandbox.close_calls == 1
    assert context.run_sandbox is None
