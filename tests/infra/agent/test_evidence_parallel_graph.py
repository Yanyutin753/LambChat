"""Real ToolNode fanout must preserve evidence without multiple LastValue clock writes."""

import asyncio

import pytest
from langchain_core.messages import AIMessage, ToolMessage
from langchain_core.tools import tool
from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt import ToolNode

from src.infra.agent.middleware.evidence import EvidenceClock, EvidenceMiddleware, EvidenceState


async def _writer(record, content):
    return f"/evidence/{record['evidence_id']}.json"


def _graph(middleware, tools):
    graph = StateGraph(EvidenceState)
    graph.add_node("initialize", lambda state: middleware.before_agent(state, None))
    graph.add_node("tools", ToolNode(tools, awrap_tool_call=middleware.awrap_tool_call))
    graph.add_node(
        "revalidate",
        lambda state: {"evidence": middleware.clock.invalidate_old(state.get("evidence", []))},
    )
    graph.add_edge(START, "initialize")
    graph.add_edge("initialize", "tools")
    graph.add_edge("tools", "revalidate")
    graph.add_edge("revalidate", END)
    return graph.compile()


@pytest.mark.parametrize("mutation", [False, True])
async def test_parallel_toolnode_evidence_does_not_conflict_or_accept_inflight_old_proof(mutation):
    read_started = asyncio.Event()
    write_finished = asyncio.Event()

    @tool
    async def observe() -> str:
        """Read a workspace observation."""
        read_started.set()
        await write_finished.wait()
        return "observation"

    @tool("write_file" if mutation else "lookup")
    async def second() -> str:
        """Complete another workspace operation alongside the read."""
        await read_started.wait()
        write_finished.set()
        return "operation complete"

    clock = EvidenceClock()
    middleware = EvidenceMiddleware(
        session_id="s", run_id="r", scope_version="v", writer=_writer, clock=clock
    )
    result = await _graph(middleware, [observe, second]).ainvoke(
        {
            "messages": [
                AIMessage(
                    content="",
                    tool_calls=[
                        {"name": "observe", "args": {}, "id": "read", "type": "tool_call"},
                        {"name": second.name, "args": {}, "id": "second", "type": "tool_call"},
                    ],
                )
            ],
        }
    )

    records = {item["tool_call_id"]: item for item in result["evidence"]}
    assert set(records) == {"read", "second"}
    assert {
        message.tool_call_id for message in result["messages"] if isinstance(message, ToolMessage)
    } == {"read", "second"}
    assert clock.active_writes == 0
    if mutation:
        assert clock.generation == 2
        assert records["read"]["status"] == "stale"
        assert not clock.current(records["read"])
        assert records["second"]["status"] == "observed"
        assert clock.current(records["second"])
    else:
        assert all(
            item["status"] == "observed" and clock.current(item) for item in records.values()
        )


@pytest.mark.parametrize("different_execution", [False, True])
async def test_graph_clock_revalidation_only_expires_proof_from_old_generation_or_execution(
    different_execution,
):
    @tool
    async def observe() -> str:
        """Read current workspace evidence."""
        return "fresh observation"

    clock = EvidenceClock(generation=2)
    old_clock = EvidenceClock() if different_execution else clock
    old = {
        "evidence_id": "old-proof",
        "tool_call_id": "old",
        "status": "observed",
        "source_ref": "/evidence/old.json",
        "session_id": "s",
        "run_id": "r",
        "scope_version": "v",
        "evidence_clock_token": old_clock.token,
        "evidence_clock_generation": 0,
    }
    middleware = EvidenceMiddleware(
        session_id="s", run_id="r", scope_version="v", writer=_writer, clock=clock
    )
    result = await _graph(middleware, [observe]).ainvoke(
        {
            "evidence": [old],
            "_evidence_clock_token": old_clock.token,
            "_evidence_clock_generation": 0,
            "messages": [
                AIMessage(
                    content="",
                    tool_calls=[
                        {"name": "observe", "args": {}, "id": "fresh", "type": "tool_call"}
                    ],
                )
            ],
        }
    )
    records = {item["tool_call_id"]: item for item in result["evidence"]}
    assert records["old"]["status"] == "stale"
    assert not clock.current(records["old"])
    assert records["fresh"]["status"] == "observed"
    assert clock.current(records["fresh"])
    assert result["_evidence_clock_token"] == clock.token
