from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from src.infra.agent.middleware.evidence import EvidenceClock
from src.infra.goal import build_goal_input, create_goal_rubric_middleware
from src.infra.persistent_goal import GoalService
from src.kernel.schemas.persistent_goal import PersistentGoalCreate
from tests.infra.agent.test_persistent_goal import Store


@pytest.fixture
async def audit(monkeypatch):
    service = GoalService(Store())
    value = await service.create(
        "s",
        "u",
        PersistentGoalCreate(objective="Deliver report", rubric="Verify totals\nSave report"),
    )
    value = await service.reserve("s", "u", value.version)
    monkeypatch.setattr("src.infra.persistent_goal.GoalService", lambda: service)
    monkeypatch.setattr(
        "src.infra.agent.evidence.load_grader_evidence",
        AsyncMock(return_value=("original", {"proof"})),
    )
    presenter = SimpleNamespace(run_id=value.current_run_id)
    clock = EvidenceClock()
    goal = {
        "objective": value.objective,
        "rubric": value.rubric,
        "_persistent_id": value.id,
        "_persistent_version": value.version,
    }
    middleware = create_goal_rubric_middleware(
        model=object(),
        goal=goal,
        presenter=presenter,
        backend=object(),
        session_id="s",
        user_id="u",
        evidence_clock=clock,
    )
    runtime = SimpleNamespace(
        state={"messages": [], "evidence": []}, tool_call_id="audit", config={}
    )
    return middleware, runtime, presenter, clock, service, goal


async def complete(audit):
    middleware, runtime, *_ = audit
    return await middleware.tools[1].coroutine(status="complete", runtime=runtime)


async def test_persistent_goal_self_audits_without_a_grader_and_preserves_legacy_nodes(audit):
    middleware, runtime, presenter, _, _, goal = audit
    assert middleware.name == "_RetryableRubricMiddleware"
    assert (
        build_goal_input(HumanMessage("continue"), goal, rubric_middleware=middleware).get("rubric")
        is None
    )
    result = await complete(audit)
    runtime.state.update(result.update)
    await middleware.aafter_agent(runtime.state, runtime)
    assert presenter.goal_verdict["result"] == "satisfied"
    assert presenter.goal_evidence_ids == ["proof"]
    assert middleware._grader is None


async def test_blocked_requires_an_explicit_reason(audit):
    middleware, runtime, presenter, *_ = audit
    result = await middleware.tools[1].coroutine(status="blocked", runtime=runtime)
    assert result["status"] == "error"
    assert not getattr(presenter, "goal_verdict", None)


@pytest.mark.parametrize("change", ["write", "steer", "pause", "restore"])
async def test_audit_is_invalidated_by_later_activity_or_authority_change(audit, change):
    middleware, runtime, presenter, clock, service, _ = audit
    result = await complete(audit)
    runtime.state.update(result.update)
    if change == "write":
        clock.generation += 1
    elif change == "restore":
        clock.token = "new-owner"
    elif change == "steer":
        runtime.state["_steer_applied"] = {"new-request": 123}
        runtime.state["messages"].append(HumanMessage("Also verify subtotals"))
    else:
        await service.control("s", "u", "pause")
    await middleware.aafter_agent(runtime.state, runtime)
    assert not getattr(presenter, "goal_evidence_ready", False)
    assert getattr(presenter, "goal_verdict", {}).get("result") != "satisfied"


async def test_goal_tools_do_not_change_the_prefix_when_goal_changes(audit):
    middleware, runtime, _, _, _, goal = audit
    first = [(t.name, t.description, t.args) for t in middleware.tools]
    other = create_goal_rubric_middleware(
        model=object(),
        goal={**goal, "objective": "Different task"},
        session_id="other",
        user_id="other",
        presenter=SimpleNamespace(run_id="other"),
        backend=object(),
        evidence_clock=EvidenceClock(),
    )
    assert first == [(t.name, t.description, t.args) for t in other.tools]


async def test_no_audit_never_implies_success_even_with_an_old_grader_verdict(audit):
    middleware, runtime, presenter, *_ = audit
    runtime.state.update(
        _rubric_status="satisfied", _rubric_criteria=[{"name": "old", "passed": True}]
    )
    runtime.state["messages"] = [AIMessage(content="Done")]
    await middleware.aafter_agent(runtime.state, runtime)
    assert presenter.goal_verdict["result"] == "needs_revision"


async def test_blocked_requires_three_consecutive_turns_with_the_same_reason(audit):
    from src.infra.persistent_goal import advance_goal

    _, _, _, _, service, _ = audit
    value = await service.get("s", "u")
    for turn in range(3):
        value = advance_goal(
            value,
            usage=2,
            verdict={"result": "blocked", "explanation": "Missing user credential"},
            tools=0,
        )
        assert value.status == ("blocked" if turn == 2 else "active")
    value.status = "active"
    value = advance_goal(
        value, usage=2, verdict={"result": "blocked", "explanation": "Different blocker"}, tools=0
    )
    assert value.status == "active"
    assert value.blocked_turns == 1


async def test_get_and_update_goal_are_not_progress_or_self_proving_evidence():
    from src.infra.goal_runtime import GoalRunMetrics

    metrics = GoalRunMetrics()
    for name in ("get_goal", "update_goal"):
        metrics.observe({"event": "tool:start", "data": {"id": name, "tool": name}})
        metrics.observe({"event": "tool:result", "data": {"id": name, "result": {"turn": 123}}})
    assert metrics.progress_signature == ""


async def test_pending_steer_invalidates_audit_even_before_it_reaches_checkpoint(
    audit, monkeypatch
):
    from src.infra.agent.middleware.goal_self_audit import audit_has_pending_input

    queue = SimpleNamespace(
        list_items=AsyncMock(return_value=[SimpleNamespace(id="new")]),
        list_receipts=AsyncMock(return_value=[]),
    )
    monkeypatch.setattr("src.infra.task.steer.get_steer_queue", lambda: queue)
    assert await audit_has_pending_input("s", [])
    queue.list_items.return_value = []
    queue.list_receipts.return_value = [SimpleNamespace(id="new")]
    assert await audit_has_pending_input("s", [])
    assert not await audit_has_pending_input("s", ["new"])


async def test_compiled_graph_persists_tool_audit_and_never_invokes_grader(audit):
    from langchain.agents import create_agent
    from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
    from langgraph.checkpoint.memory import InMemorySaver

    middleware, runtime, presenter, *_ = audit
    current = await middleware.get_goal(runtime.state)

    class Model(FakeMessagesListChatModel):
        def bind_tools(self, tools, **kwargs):
            return self

    model = Model(
        responses=[
            AIMessage(
                content="",
                tool_calls=[{"name": "get_goal", "id": "read-goal", "args": {}}],
            ),
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "update_goal",
                        "id": "audit",
                        "args": {
                            "status": "complete",
                            "explanation": "All verified",
                            "criteria": [
                                {"requirement_id": row["id"], "evidence_ids": ["proof"]}
                                for row in current["requirements"]
                            ],
                        },
                    }
                ],
            ),
            AIMessage(content="Delivered"),
        ]
    )
    saver = InMemorySaver()
    graph = create_agent(model, middleware=[middleware], checkpointer=saver)
    config = {"configurable": {"thread_id": "audit-test"}}
    await graph.ainvoke({"messages": [HumanMessage("Finish")]}, config)
    assert presenter.goal_verdict["result"] == "satisfied"
    snapshot = await graph.aget_state(config)
    assert snapshot.values["_goal_audit"]["verdict"]["result"] == "satisfied"
    from langchain_core.messages.utils import convert_to_openai_messages

    wire_messages = convert_to_openai_messages(snapshot.values["messages"])
    read_result = next(item for item in wire_messages if item.get("tool_call_id") == "read-goal")
    assert "Verify totals" in read_result["content"]
    assert "tokens_used" not in read_result["content"]
    assert "artifact" not in read_result
    assert middleware._grader is None


async def test_pending_input_prevents_completion_and_stagnation_stop(audit):
    from src.infra.persistent_goal import advance_goal

    _, _, _, _, service, _ = audit
    value = await service.get("s", "u")
    value.stagnant_turns = 5
    result = advance_goal(
        value,
        usage=1,
        verdict={"result": "satisfied", "criteria": [{"passed": True, "evidence_ids": ["proof"]}]},
        tools=1,
        evidence_ready=True,
        evidence_ids=["proof"],
        pending_input=True,
    )
    assert result.status == "active"
    assert result.last_verdict is None


async def test_old_checkpoint_at_grader_hook_resumes_without_grading(audit):
    from langchain.agents import create_agent
    from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
    from langgraph.checkpoint.memory import InMemorySaver

    class Model(FakeMessagesListChatModel):
        def bind_tools(self, tools, **kwargs):
            return self

    middleware, _, presenter, *_ = audit
    model = Model(responses=[AIMessage(content="Legacy partial result")])
    old = create_goal_rubric_middleware(
        model=model, goal={"objective": "Deliver report", "rubric": "Verify totals"}
    )
    saver = InMemorySaver()
    config = {"configurable": {"thread_id": "legacy-goal"}}
    graph = create_agent(
        model,
        middleware=[old],
        checkpointer=saver,
        interrupt_before=["_RetryableRubricMiddleware.after_agent"],
    )
    await graph.ainvoke({"messages": [HumanMessage("Work")], "rubric": "Verify totals"}, config)
    assert (await graph.aget_state(config)).next == ("_RetryableRubricMiddleware.after_agent",)
    restored = create_agent(model, middleware=[middleware], checkpointer=saver)
    await restored.ainvoke(None, config)
    assert presenter.goal_verdict["result"] == "needs_revision"
    assert middleware._grader is None


async def test_later_failed_audit_cannot_reuse_an_earlier_completion(audit):
    middleware, runtime, presenter, *_ = audit
    runtime.state.update((await complete(audit)).update)
    runtime.state["messages"].append(
        AIMessage(
            content="",
            tool_calls=[{"name": "update_goal", "id": "rejected", "args": {"status": "complete"}}],
        )
    )
    await middleware.aafter_agent(runtime.state, runtime)
    assert presenter.goal_verdict["result"] != "satisfied"


async def test_explicit_user_pause_can_be_reported_by_main_agent_without_claiming_completion(audit):
    from src.infra.persistent_goal import advance_goal

    middleware, runtime, presenter, clock, service, _ = audit
    result = await middleware.tools[1].coroutine(
        status="paused", explanation="User explicitly requested pausing this Goal", runtime=runtime
    )
    runtime.state.update(result.update)
    clock.generation += 1  # A user pause does not require unchanged workspace proof.
    await middleware.aafter_agent(runtime.state, runtime)
    assert presenter.goal_verdict["result"] == "paused"
    value = await service.get("s", "u")
    value = advance_goal(value, usage=1, verdict=presenter.goal_verdict, tools=1)
    assert value.status == "paused"
    assert value.stop_reason == "user_paused"
    assert value.current_run_id is None


async def test_completion_needs_only_status_and_keeps_server_evidence_checks(audit, monkeypatch):
    from src.infra.persistent_goal import advance_goal

    middleware, runtime, presenter, _, service, _ = audit
    update = middleware.tools[1]
    assert "criteria" not in update.args
    result = await update.coroutine(status="complete", runtime=runtime)
    runtime.state.update(result.update)
    await middleware.aafter_agent(runtime.state, runtime)
    value = await service.get("s", "u")
    finished = advance_goal(
        value,
        usage=1,
        verdict=presenter.goal_verdict,
        tools=1,
        evidence_ready=presenter.goal_evidence_ready,
        evidence_ids=presenter.goal_evidence_ids,
    )
    assert finished.status == "completed"
    assert not presenter.goal_verdict.get("criteria")
    monkeypatch.setattr(
        "src.infra.agent.evidence.load_grader_evidence", AsyncMock(return_value=("", set()))
    )
    rejected = await update.coroutine(status="complete", runtime=runtime)
    assert rejected["status"] == "error"


async def test_get_goal_gives_model_plain_text_and_ui_structured_artifact(audit):
    middleware, runtime, *_ = audit
    get = middleware.tools[0]
    assert get.response_format == "content_and_artifact"
    content, artifact = await get.coroutine(runtime=runtime)
    assert "Deliver report" in content
    assert "Verify totals" in content
    assert "tokens_used" not in content
    assert '"requirements"' not in content
    assert artifact["objective"] == "Deliver report"


async def test_goal_artifact_is_displayed_without_changing_model_content(audit):
    import json

    from langchain_core.messages import ToolMessage

    from src.infra.agent.events.tool_outputs import extract_tool_output, process_messages

    middleware, runtime, *_ = audit
    content, artifact = await middleware.tools[0].coroutine(runtime=runtime)
    message = ToolMessage(content=content, artifact=artifact, name="get_goal", tool_call_id="read")
    assert extract_tool_output(message) == artifact
    assert json.loads(process_messages([message])) == artifact
    assert message.content == content


@pytest.mark.parametrize("ready,refs", [(False, ["proof"]), (True, []), (True, ["forged"])])
async def test_host_rejects_self_audit_without_current_evidence(audit, ready, refs):
    from src.infra.persistent_goal import advance_goal

    *_, service, _ = audit
    value = await service.get("s", "u")
    result = advance_goal(
        value,
        usage=1,
        tools=1,
        evidence_ready=ready,
        evidence_ids=["proof"],
        verdict={"result": "satisfied", "self_audit": True, "evidence_ids": refs},
    )
    assert result.status == "active"
