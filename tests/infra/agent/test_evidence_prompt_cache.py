"""Evidence updates must append to checkpoint history without rewriting the system prefix."""

import pytest
from langchain.agents import create_agent
from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.tools import tool
from langgraph.checkpoint.memory import InMemorySaver

from src.infra.agent.middleware.evidence import EvidenceClock, EvidenceMiddleware
from src.infra.llm.client import LLMClient


async def test_tool_evidence_keeps_system_prefix_stable_and_persists_model_context():
    calls = []

    class RecordingModel(FakeMessagesListChatModel):
        def bind_tools(self, tools, **kwargs):
            return self

        def _generate(self, messages, *args, **kwargs):
            calls.append(list(messages))
            return super()._generate(messages, *args, **kwargs)

    @tool
    def observe() -> str:
        """Read a synthetic observation."""
        return "observation"

    async def writer(record, content):
        return f"/evidence/{record['evidence_id']}.json"

    middleware = EvidenceMiddleware(session_id="s", run_id="r", scope_version="v", writer=writer)
    graph = create_agent(
        model=RecordingModel(
            responses=[
                AIMessage(content="", tool_calls=[{"name": "observe", "args": {}, "id": "call"}]),
                AIMessage(content="done"),
            ]
        ),
        tools=[observe],
        system_prompt="Stable instructions",
        middleware=[middleware],
        checkpointer=InMemorySaver(),
    )
    config = {"configurable": {"thread_id": "s"}}
    result = await graph.ainvoke({"messages": [HumanMessage(content="Observe")]}, config)

    assert len(calls) == 2
    assert [m.content for m in calls[0] if isinstance(m, SystemMessage)] == [
        m.content for m in calls[1] if isinstance(m, SystemMessage)
    ]
    snapshot = next(m for m in calls[1] if m.name == "evidence_context")
    assert snapshot.additional_kwargs.get("lambchat_evidence_snapshot") is True
    assert '"status": "observed"' in snapshot.content
    assert "/evidence/" in snapshot.content
    assert snapshot in result["messages"]
    assert calls[1][: len(calls[0])] == calls[0]
    checkpoint = await graph.aget_state(config)
    assert snapshot in checkpoint.values["messages"]


async def test_evidence_snapshot_appends_only_changes_and_preserves_old_messages():
    clock = EvidenceClock()
    middleware = EvidenceMiddleware(session_id="s", run_id="r", scope_version="v", clock=clock)
    record = {
        "evidence_id": "proof",
        "source_ref": "/evidence/proof.json",
        "scope_version": "v",
        "status": "observed",
        "evidence_clock_token": clock.token,
        "evidence_clock_generation": clock.generation,
    }
    state = {"messages": [HumanMessage(content="Observe")], "evidence": [record]}
    first = await middleware.abefore_model(state, None)
    state["messages"].extend(first["messages"])
    state["evidence"] = first["evidence"]
    original = state["messages"][-1].content
    unchanged = await middleware.abefore_model(state, None)
    assert not unchanged.get("messages")

    clock.generation += 1
    changed = await middleware.abefore_model(state, None)
    assert '"status": "stale"' in changed["messages"][0].content
    assert state["messages"][-1].content == original
    assert changed["evidence"][0]["status"] == "stale"


@pytest.mark.parametrize(
    "provider,model_name,api_format",
    [
        ("zai", "glm-5.3-flash", None),
        ("anthropic", "claude-sonnet-4-5", None),
        ("openai", "gpt-5.6-luna", None),
        ("openai", "gpt-5.6-sol", "responses"),
        ("deepseek", "deepseek-flash", "responses"),
        ("zhipu", "glm-5.3-flashx", None),
        ("google", "gemini-3.1-pro", None),
    ],
)
async def test_evidence_updates_preserve_serialized_prefix_across_protocols(
    provider, model_name, api_format
):
    model = LLMClient._create_model(provider, model_name, api_key="test-key", api_format=api_format)
    middleware = EvidenceMiddleware(session_id="s", run_id="r", scope_version="v")
    state = {"messages": [HumanMessage(content="Observe")], "evidence": []}
    original = [SystemMessage(content="Stable instructions"), *state["messages"]]
    state["evidence"] = [{"evidence_id": "proof", "status": "unavailable", "scope_version": "v"}]
    update = await middleware.abefore_model(state, None)
    extended = [*original, AIMessage(content="Observed"), *update["messages"]]

    if provider == "google":
        before = model._prepare_request(original)
        after = model._prepare_request(extended)
        assert before["config"].system_instruction == after["config"].system_instruction
        key = "contents"
    else:
        before = model._get_request_payload(original)
        after = model._get_request_payload(extended)
        assert before.get("system") == after.get("system")
        key = "input" if api_format == "responses" else "messages"
        if provider in {"anthropic", "zai"}:
            # Breakpoint metadata moves; compare the token-bearing content, not its policy.
            for payload in (before, after):
                for message in payload[key]:
                    blocks = message["content"]
                    if isinstance(blocks, str):
                        blocks = [{"type": "text", "text": blocks}]
                    message["content"] = [
                        {k: v for k, v in block.items() if k != "cache_control"} for block in blocks
                    ]
    assert after[key][: len(before[key])] == before[key]


async def test_new_turn_does_not_repeat_the_same_stale_evidence_index():
    first = EvidenceMiddleware(session_id="s", run_id="r1", scope_version="v1")
    record = {
        "evidence_id": "proof",
        "source_ref": "/evidence/proof.json",
        "scope_version": "v1",
        "status": "observed",
        "run_id": "r1",
        "evidence_clock_token": first.clock.token,
        "evidence_clock_generation": 0,
    }
    state = {"messages": [HumanMessage("Initial work")], "evidence": [record]}
    initial = await first.abefore_model(state, None)
    state["messages"].extend(initial["messages"])
    initial_content = state["messages"][-1].content

    second = EvidenceMiddleware(session_id="s", run_id="r2", scope_version="v1")
    state.update(second.before_agent(state, None))
    invalidated = await second.abefore_model(state, None)
    assert invalidated["evidence"][0]["status"] == "stale"
    assert '"status": "stale"' in invalidated["messages"][0].content
    state["messages"].extend(invalidated["messages"])
    state["evidence"] = invalidated["evidence"]

    third = EvidenceMiddleware(session_id="s", run_id="r3", scope_version="v2")
    state.update(third.before_agent(state, None))
    unchanged = await third.abefore_model(state, None)
    assert not unchanged.get("messages"), (
        "Changing run ownership must not repeat an unchanged index"
    )
    assert unchanged["evidence"][0]["status"] == "stale"
    assert state["messages"][1].content == initial_content

    fresh = {
        **record,
        "evidence_id": "fresh-proof",
        "scope_version": "v2",
        "run_id": "r3",
        "evidence_clock_token": third.clock.token,
    }
    state["evidence"].append(fresh)
    observed = await third.abefore_model(state, None)
    assert '"evidence_id": "fresh-proof"' in observed["messages"][0].content
    assert observed["evidence"][-1]["status"] == "observed"
