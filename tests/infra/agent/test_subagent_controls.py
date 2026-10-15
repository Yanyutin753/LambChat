"""Subagent concurrency and lifecycle controls reuse persistent conversations."""

import asyncio
from pathlib import Path
from types import SimpleNamespace

from langchain_core.messages import AIMessage, ToolMessage
from langgraph.checkpoint.memory import InMemorySaver

from src.infra.agent.subagent_sessions import SubagentInboxMiddleware, SubagentSessions
from src.infra.tool.subagent_tool import create_subagent_tools


class _HeldGraph:
    def __init__(self, release, entered):
        self.release, self.entered = release, entered
        self.values = {}
        self.next = ()
        self.invocations = 0

    async def aget_state(self, config):
        return SimpleNamespace(values=self.values, next=self.next, tasks=())

    async def aupdate_state(self, config, state, as_node):
        self.values = {**self.values, **state}
        self.next = ("model",)

    async def ainvoke(self, graph_input, config):
        self.invocations += 1
        self.entered.set()
        await self.release.wait()
        self.values = {"messages": [AIMessage(content="done")]}
        self.next = ()
        return self.values


def _sessions():
    release = asyncio.Event()
    graphs = {}

    async def build(role, inbox):
        graph = graphs.setdefault(inbox.subagent_id, _HeldGraph(release, asyncio.Event()))
        return graph

    return (
        SubagentSessions(
            session_id="controls", user_id="owner", build_graph=build, checkpointer=InMemorySaver()
        ),
        graphs,
        release,
    )


async def test_three_execute_fourth_queues_and_queued_cancel_is_idempotent():
    sessions, graphs, release = _sessions()
    try:
        ids = []
        for index in range(4):
            result = await sessions.start(
                "reviewer", "work", call_id=str(index), config={}, background=True
            )
            ids.append(result["subagent_id"])
        for key in ids[:3]:
            await asyncio.wait_for(graphs[key].entered.wait(), 1)
        await asyncio.sleep(0)
        assert [sessions.result(key)["status"] for key in ids] == ["running"] * 3 + ["queued"]
        assert not graphs[ids[3]].entered.is_set()
        assert (await sessions.cancel(ids[3]))["status"] == "cancelled"
        assert await sessions.cancel(ids[3]) == sessions.result(ids[3])
        listed = sessions.list_subagents()
        assert len(listed["subagents"]) == 4
        assert listed == sessions.list_subagents()
        assert (await sessions.cancel(ids[0]))["status"] == "cancelled"
        assert sessions.result(ids[1])["status"] == "running"
        assert (await sessions.wait(ids[0], config={}))["status"] == "cancelled"
    finally:
        release.set()
        await sessions.close()


async def test_wait_is_bounded_and_does_not_cancel_child(monkeypatch):
    monkeypatch.setattr(
        "src.infra.agent.subagent_sessions.SUBAGENT_WAIT_TIMEOUT_SECONDS", 0.01, raising=False
    )
    sessions, graphs, release = _sessions()
    try:
        result = await sessions.start(
            "reviewer", "work", call_id="bounded", config={}, background=True
        )
        key = result["subagent_id"]
        await asyncio.wait_for(graphs[key].entered.wait(), 1)
        waited = await asyncio.wait_for(sessions.wait(key, config={}), 0.2)
        assert waited["status"] == "running"
        assert not sessions.jobs[key].done()
    finally:
        release.set()
        await sessions.close()


async def test_execution_times_out_and_parent_close_converges_all_states(monkeypatch):
    monkeypatch.setattr(
        "src.infra.agent.subagent_sessions.SUBAGENT_EXECUTION_TIMEOUT_SECONDS", 0.01, raising=False
    )
    sessions, graphs, release = _sessions()
    result = await sessions.start("reviewer", "work", call_id="timeout", config={}, background=True)
    await asyncio.wait_for(sessions.jobs[result["subagent_id"]], 0.3)
    assert sessions.result(result["subagent_id"])["status"] == "timed_out"
    assert "600" not in sessions.result(result["subagent_id"])["error"]
    await sessions.close()
    assert all(job.done() for job in sessions.jobs.values())
    assert (await sessions.cancel("foreign"))["status"] == "error"


def test_cancel_and_list_have_dedicated_callable_controls():
    sessions, _, _ = _sessions()
    tools = {tool.name: tool for tool in create_subagent_tools(sessions)}
    assert {"cancel_subagent", "list_subagents"}.issubset(tools)
    assert set(tools["cancel_subagent"].args) == {"subagent_id"}
    assert tools["list_subagents"].args == {}
    assert "bounded" in tools["wait_subagent"].description.lower()


def test_all_three_modes_use_shared_session_assembly_and_parent_cleanup():
    for mode in ("search_agent", "team_agent"):
        source = Path(f"src/agents/{mode}/nodes.py").read_text()
        assert "assemble_subagent_sessions(" in source
        assert "await subagent_sessions.close(" in source
    helper = Path("src/infra/agent/subagent_assembly.py").read_text()
    assert "create_sub_agent(" in helper
    assert "fork_types=" in helper
    assert "resolve_spec" in helper


async def test_duplicate_coordinators_do_not_execute_same_child_twice():
    sessions, graphs, release = _sessions()
    other = SubagentSessions(
        session_id=sessions.session_id,
        user_id=sessions.user_id,
        build_graph=sessions.build_graph,
        checkpointer=sessions.checkpointer,
    )
    try:
        first = await sessions.start("reviewer", "work", call_id="same", config={}, background=True)
        key = first["subagent_id"]
        await asyncio.wait_for(graphs[key].entered.wait(), 1)
        other.restore(sessions.snapshot())
        waited = await other.wait(key, config={})
        assert waited["status"] == "failed"
        assert graphs[key].invocations == 1
        assert not sessions.jobs[key].done()
    finally:
        release.set()
        await sessions.close()
        await other.close()


async def test_recovery_pauses_uncertain_external_tool_call_without_replaying():
    sessions, graphs, release = _sessions()
    key = "subagent-uncertain"
    sessions.records[key] = {
        "subagent_type": "reviewer",
        "status": "running",
        "description": "write",
        "pending": [],
    }
    graph = graphs[key] = _HeldGraph(release, asyncio.Event())
    graph.values = {
        "messages": [
            AIMessage(
                content="",
                tool_calls=[
                    {"name": "external_write", "args": {}, "id": "write-1", "type": "tool_call"}
                ],
            )
        ]
    }
    graph.next = ("tools",)
    result = await sessions.wait(key, config={})
    assert result["status"] == "waiting_human"
    assert result["verification_required"] is True
    assert graph.invocations == 0
    assert sessions.jobs == {}


async def test_approval_wait_does_not_consume_execution_deadline(monkeypatch):
    monkeypatch.setattr(
        "src.infra.agent.subagent_sessions.SUBAGENT_EXECUTION_TIMEOUT_SECONDS", 0.03, raising=False
    )
    sessions, graphs, release = _sessions()
    release.set()
    original = sessions.build_graph

    async def build(role, inbox):
        graph = await original(role, inbox)

        async def approve(graph_input, config):
            return {"__interrupt__": ["approval"]}

        graph.ainvoke = approve
        return graph

    sessions.build_graph = build
    result = await sessions.start(
        "reviewer", "work", call_id="approval", config={}, background=True
    )
    key = result["subagent_id"]
    await sessions.jobs[key]
    used = sessions.records[key]["execution_seconds"]
    assert sessions.result(key)["status"] == "waiting_human"
    await asyncio.sleep(0.04)
    assert sessions.result(key)["status"] == "waiting_human"
    assert sessions.records[key]["execution_seconds"] == used
    await sessions.close()
    assert sessions.result(key)["status"] == "waiting_human"


async def test_distributed_child_lease_blocks_duplicate_writer_and_releases_token(monkeypatch):
    sessions, graphs, release = _sessions()
    leases = {}

    class Redis:
        async def set(self, key, value, *, nx, ex):
            if key in leases:
                return False
            leases[key] = value
            return True

        async def eval(self, script, numkeys, key, token):
            if leases.get(key) == token:
                leases.pop(key)
                return 1
            return 0

    class Storage:
        async def get_by_session_id(self, key):
            return SimpleNamespace(metadata={"current_run_id": "run-1"})

    monkeypatch.setattr("src.infra.session.storage.SessionStorage", Storage)
    monkeypatch.setattr("src.infra.storage.redis.get_redis_client", Redis)
    other = SubagentSessions(
        session_id=sessions.session_id,
        user_id=sessions.user_id,
        build_graph=sessions.build_graph,
        checkpointer=InMemorySaver(),
    )
    config = {"configurable": {"run_id": "run-1"}}
    try:
        first = await sessions.start(
            "reviewer", "work", call_id="leased", config=config, background=True
        )
        key = first["subagent_id"]
        await asyncio.wait_for(graphs[key].entered.wait(), 1)
        assert len(leases) == 1
        other.restore(sessions.snapshot())
        assert (await other.wait(key, config=config))["status"] == "failed"
        assert graphs[key].invocations == 1
        await sessions.cancel(key)
        assert leases == {}
    finally:
        release.set()
        await sessions.close()
        await other.close()


async def test_changed_parent_owner_cannot_execute_child(monkeypatch):
    sessions, graphs, release = _sessions()

    class Storage:
        async def get_by_session_id(self, key):
            return SimpleNamespace(metadata={"current_run_id": "new-run"})

    monkeypatch.setattr("src.infra.session.storage.SessionStorage", Storage)
    try:
        first = await sessions.start(
            "reviewer",
            "work",
            call_id="old",
            config={"configurable": {"run_id": "old-run"}},
            background=True,
        )
        await sessions.jobs[first["subagent_id"]]
        assert sessions.result(first["subagent_id"])["status"] == "failed"
        assert graphs[first["subagent_id"]].invocations == 0
    finally:
        release.set()
        await sessions.close()


async def test_shared_assembly_reloads_authorized_tools_and_role_filters():
    from src.infra.agent.subagent_assembly import refresh_subagent_context

    class Context:
        def __init__(self, **values):
            self.__dict__.update(values)
            self.tools = []
            self.skills = []

        async def setup(self):
            self.skills = [{"name": "allowed"}]

        async def get_tools(self):
            self.tools = ["currently-authorized"]
            return self.tools

    original = Context(
        **{
            field: None
            for field in (
                "session_id",
                "agent_id",
                "user_id",
                "disabled_tools",
                "disabled_skills",
                "enabled_skills",
                "disabled_mcp_tools",
                "enabled_mcp_servers",
                "auto_mode",
            )
        }
    )
    original.disabled_skills = ["revoked"]
    original.enabled_mcp_servers = ["allowed-server"]
    original.tools = ["stale-revoked-tool"]
    fresh = await refresh_subagent_context(original)
    assert fresh is not original
    assert fresh.disabled_skills == ["revoked"]
    assert fresh.enabled_mcp_servers == ["allowed-server"]
    assert fresh.tools == ["currently-authorized"]
    assert original.tools == ["stale-revoked-tool"]


async def test_object_id_session_parent_ownership_uses_database_id_fallback(monkeypatch):
    """POST /api/sessions uses ObjectId IDs and need not set custom session_id."""
    sessions, _, release = _sessions()
    lookups = []
    leases = {}

    class Storage:
        async def get_by_session_id(self, key):
            lookups.append(("custom", key))
            return None

        async def get_by_id(self, key):
            lookups.append(("object", key))
            return SimpleNamespace(user_id="owner", metadata={"current_run_id": "run-1"})

    class Redis:
        async def set(self, key, value, **kwargs):
            leases[key] = value
            return True

        async def eval(self, script, numkeys, key, token):
            leases.pop(key, None)
            return 1

    monkeypatch.setattr("src.infra.session.storage.SessionStorage", Storage)
    monkeypatch.setattr("src.infra.storage.redis.get_redis_client", Redis)
    sessions.session_id = "507f1f77bcf86cd799439011"
    sessions.configs["child"] = {"configurable": {"run_id": "run-1"}}
    async with sessions._runner_ownership("child"):
        assert lookups == [("custom", sessions.session_id), ("object", sessions.session_id)]
        assert len(leases) == 1
    assert leases == {}
    await sessions.close()


async def test_long_task_can_finish_after_forty_five_minutes_without_deadline_cancel(monkeypatch):
    real_timeout = asyncio.timeout
    # Scale the production deadline and a 45-minute execution by the same factor.
    monkeypatch.setattr(
        "src.infra.agent.subagent_sessions.asyncio.timeout",
        lambda seconds: real_timeout(seconds / 10000),
    )
    sessions, graphs, release = _sessions()
    try:
        started = await sessions.start(
            "reviewer", "long tool", call_id="long-tool", config={}, background=True
        )
        key = started["subagent_id"]
        await asyncio.wait_for(graphs[key].entered.wait(), 1)
        await asyncio.sleep(2700 / 10000)
        release.set()
        await sessions.jobs[key]
        assert sessions.result(key)["status"] == "completed"
    finally:
        release.set()
        await sessions.close()


async def test_timeout_preserves_checkpoint_progress_and_tool_results_after_restore(monkeypatch):
    monkeypatch.setattr(
        "src.infra.agent.subagent_sessions.SUBAGENT_EXECUTION_TIMEOUT_SECONDS", 0.05
    )
    sessions, graphs, release = _sessions()
    try:
        started = await sessions.start(
            "reviewer", "work", call_id="partial", config={}, background=True
        )
        key = started["subagent_id"]
        await graphs[key].entered.wait()
        graphs[key].values["messages"].insert(0, AIMessage(content="inherited parent history"))
        graphs[key].values["messages"] += [
            AIMessage(
                content="Found the cause",
                tool_calls=[{"name": "read_file", "args": {}, "id": "read", "type": "tool_call"}],
            ),
            ToolMessage(content="verified file contents", name="read_file", tool_call_id="read"),
            AIMessage(
                content="Now checking the fix",
                tool_calls=[{"name": "slow_tool", "args": {}, "id": "slow", "type": "tool_call"}],
            ),
        ]
        await sessions.jobs[key]
        result = sessions.result(key)
        assert result["status"] == "timed_out"
        assert result["partial_result"] is True
        assert "Found the cause" in result["result"]
        assert "inherited parent history" not in result["result"]
        assert "verified file contents" in result["result"]
        assert "slow_tool" in result["result"]
        assert "unconfirmed" in result["result"]
        other, _, _ = _sessions()
        other.restore(sessions.snapshot())
        assert other.result(key) == result
        assert (await other.wait(key, config={}))["result"] == result["result"]
        assert not other.jobs
        assert graphs[key].invocations == 1
    finally:
        release.set()
        await sessions.close()


async def test_checkpoint_read_failure_still_emits_terminal_timeout(monkeypatch):
    monkeypatch.setattr(
        "src.infra.agent.subagent_sessions.SUBAGENT_EXECUTION_TIMEOUT_SECONDS", 0.05
    )
    sessions, graphs, release = _sessions()
    try:
        started = await sessions.start(
            "reviewer", "work", call_id="read-failure", config={}, background=True
        )
        key = started["subagent_id"]
        await graphs[key].entered.wait()

        async def unreadable(_config):
            raise OSError("checkpoint unavailable")

        graphs[key].aget_state = unreadable
        sessions.completed_tools[key] = {
            "read": ToolMessage("cached output survives storage failure", tool_call_id="read")
        }
        await sessions.jobs[key]
        assert sessions.result(key)["status"] == "timed_out"
        assert "could not be read" in sessions.result(key)["error"]
        assert "cached output survives storage failure" in sessions.result(key)["result"]
        assert sessions.emitted_states[key] == ("completed", "timed_out")
    finally:
        release.set()
        await sessions.close()


async def test_timeout_keeps_returned_tool_before_parallel_batch_checkpoint(monkeypatch):
    monkeypatch.setattr(
        "src.infra.agent.subagent_sessions.SUBAGENT_EXECUTION_TIMEOUT_SECONDS", 0.05
    )
    sessions, graphs, release = _sessions()
    try:
        started = await sessions.start(
            "reviewer", "work", call_id="parallel-partial", config={}, background=True
        )
        key = started["subagent_id"]
        await graphs[key].entered.wait()
        graphs[key].values["messages"].append(
            AIMessage(
                content="",
                tool_calls=[
                    {"id": "fast", "name": "read_file", "args": {}, "type": "tool_call"},
                    {"id": "slow", "name": "slow_tool", "args": {}, "type": "tool_call"},
                ],
            )
        )

        async def completed(_request):
            return ToolMessage(
                "returned before batch checkpoint", name="read_file", tool_call_id="fast"
            )

        inbox = SubagentInboxMiddleware(sessions, key)
        returned = await inbox.awrap_tool_call(SimpleNamespace(tool_call={"id": "fast"}), completed)
        assert returned.tool_call_id == "fast"
        await sessions.jobs[key]
        result = sessions.result(key)
        assert "returned before batch checkpoint" in result["result"]
        assert "Tool slow_tool (slow): result unconfirmed" in result["result"]
        assert "Tool read_file (fast): result unconfirmed" not in result["result"]
    finally:
        release.set()
        await sessions.close()


async def test_restart_after_timeout_uses_child_terminal_checkpoint_with_stale_parent(monkeypatch):
    events = []

    async def capture(_name, data, config):
        events.append((data["phase"], data["status"]))

    monkeypatch.setattr("src.infra.agent.subagent_sessions.adispatch_custom_event", capture)
    monkeypatch.setattr(
        "src.infra.agent.subagent_sessions.SUBAGENT_EXECUTION_TIMEOUT_SECONDS", 0.05
    )
    sessions, graphs, release = _sessions()
    try:
        started = await sessions.start(
            "reviewer", "work", call_id="durable-timeout", config={}, background=True
        )
        key = started["subagent_id"]
        await graphs[key].entered.wait()
        parent_checkpoint = sessions.snapshot()
        sessions.completed_tools[key] = {
            "read": ToolMessage("durable batch output", tool_call_id="read")
        }
        await sessions.jobs[key]
        other = SubagentSessions(
            session_id=sessions.session_id,
            user_id=sessions.user_id,
            build_graph=sessions.build_graph,
            checkpointer=sessions.checkpointer,
        )
        other.restore(parent_checkpoint)
        before_recovery = len(events)
        result = await other.wait(key, config={})
        assert events[before_recovery:] == [("started", "timed_out"), ("completed", "timed_out")]
        assert result["status"] == "timed_out"
        assert "durable batch output" in result["result"]
        assert other.emitted_states[key] == ("completed", "timed_out")
        assert not other.jobs
        assert graphs[key].invocations == 1
        replay = SubagentSessions(
            session_id=sessions.session_id,
            user_id=sessions.user_id,
            build_graph=sessions.build_graph,
            checkpointer=sessions.checkpointer,
        )
        replay.restore(parent_checkpoint)
        assert (
            await replay.start(
                "reviewer", "work", call_id="durable-timeout", config={}, background=True
            )
        )["status"] == "timed_out"
        assert replay.emitted_states[key] == ("completed", "timed_out")
        assert not replay.jobs
        assert (await other.send(key, "retry writes", config={}))["status"] == "timed_out"
    finally:
        release.set()
        await sessions.close()
