from types import SimpleNamespace

from src.infra.agent.middleware.main_agent_context import MainAgentContextMiddleware


def test_snapshot_cache_key_uses_message_ids_across_request_instances() -> None:
    messages = [SimpleNamespace(id="m1"), SimpleNamespace(id="m2")]
    first = SimpleNamespace(runtime=object())
    second = SimpleNamespace(runtime=object())

    assert MainAgentContextMiddleware._cache_key(
        first, messages
    ) == MainAgentContextMiddleware._cache_key(second, list(messages))
