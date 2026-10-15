from src.agents.search_agent.context import SearchAgentContext
from src.agents.team_agent.context import TeamAgentContext


class _CloseableSandbox:
    def __init__(self) -> None:
        self.close_calls = 0

    async def aclose(self) -> None:
        self.close_calls += 1


def test_team_agent_context_generates_fresh_default_session_id_per_instance() -> None:
    first = TeamAgentContext()
    second = TeamAgentContext()

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


def test_search_initial_tools_keep_same_order_after_loader_reordering():
    from types import SimpleNamespace

    a = SimpleNamespace(name="alpha")
    z = SimpleNamespace(name="zebra")
    first = SearchAgentContext()
    second = SearchAgentContext()
    first._append_unique_tools([z, a])
    second._append_unique_tools([a, z])
    assert (
        [tool.name for tool in first.tools]
        == [tool.name for tool in second.tools]
        == ["alpha", "zebra"]
    )
