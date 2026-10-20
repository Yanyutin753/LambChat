"""Checks for the passive observer used by the opt-in real scheduler cohort."""

import runpy
from pathlib import Path

import pytest
from langchain_core.messages import HumanMessage, SystemMessage


def helpers():
    return runpy.run_path(str(Path(__file__).with_name("live_natural.py")))


def test_natural_settings_enable_only_a_dedicated_frozen_cohort():
    configure = helpers()["natural_settings"]
    case = {"natural_idle": True, "sources": [{"agent_id": "quick"}]}
    assert configure([{}]) == {}
    assert configure([case]) == {
        "MEMORY_EXTRACTION_ENABLED": True,
        "MEMORY_EXTRACTION_IDLE_SECONDS": 60,
        "MEMORY_EXTRACTION_INTERVAL_SECONDS": 3,
    }
    for invalid in ([case, {}], [{"natural_idle": True, "sources": [{}]}]):
        with pytest.raises(ValueError):
            configure(invalid)


def test_background_phase_requires_the_exact_system_prompt_not_quoted_text():
    classify = helpers()["observed_phase"]
    prompt = "Frozen extraction policy"
    assert classify([[SystemMessage(prompt), HumanMessage("facts")]], "chat", prompt) == (
        "background_extraction"
    )
    for messages in (
        [SystemMessage("Chat policy"), HumanMessage(prompt)],
        [HumanMessage(prompt)],
        [SystemMessage(prompt + " altered"), HumanMessage("facts")],
    ):
        assert classify([messages], "chat", prompt) == "chat"
    assert classify([[SystemMessage(prompt)]], "extraction", prompt) == "extraction"


def test_passive_receipt_requires_a_real_scheduled_fire_and_filters_other_jobs(tmp_path):
    from types import SimpleNamespace

    from apscheduler.events import EVENT_JOB_EXECUTED

    observe = helpers()["record_scheduler_fire"]
    output = tmp_path / "fires.jsonl"
    for job, when in (("other", "later"), ("memory.extraction", None)):
        observe(SimpleNamespace(job_id=job, scheduled_run_time=when), output, "hash")
    assert not output.exists()
    import json
    from datetime import datetime, timezone

    scheduled = datetime(2026, 10, 20, tzinfo=timezone.utc)
    observe(
        SimpleNamespace(
            code=EVENT_JOB_EXECUTED,
            job_id="memory.extraction",
            scheduled_run_time=scheduled,
            retval={"users": 1, "dispatched": 1},
            exception=None,
        ),
        output,
        "hash",
    )
    receipt = json.loads(output.read_text())
    assert receipt["scheduled_at"] == scheduled.isoformat()
    assert receipt["result"] == {"users": 1, "dispatched": 1}
    assert receipt["source_sha256"] == "hash"
    assert output.stat().st_mode & 0o077 == 0


def test_natural_wait_observes_idle_and_two_unchanged_ticks_without_control_calls(tmp_path):
    from datetime import datetime, timezone
    from types import SimpleNamespace

    wait = helpers()["wait_for_natural_extraction"]
    updated = datetime(2026, 10, 20, tzinfo=timezone.utc)
    clock = SimpleNamespace(now=updated.timestamp())

    def advance(seconds):
        clock.now += seconds

    wait.__globals__["time"] = SimpleNamespace(
        time=lambda: clock.now, monotonic=lambda: clock.now, sleep=advance
    )
    job = {"status": "succeeded", "extracted_updated_at": updated}
    eligible = updated.timestamp() + 60

    def rows(path):
        if path.name == "model-calls.jsonl":
            return (
                [{"event": "start", "phase": "background_extraction", "time": eligible}]
                if clock.now >= eligible
                else []
            )
        return [
            {"scheduled_at": datetime.fromtimestamp(t, timezone.utc).isoformat(), "exception": None}
            for t in (eligible + 3, eligible + 6)
            if t <= clock.now
        ]

    wait.__globals__["_rows"] = rows

    class DB:
        def __getitem__(self, name):
            return SimpleNamespace(find_one=lambda query: {"updated_at": updated})

        native_memories = SimpleNamespace(count_documents=lambda q: int(clock.now >= eligible + 2))
        memory_extraction_jobs = SimpleNamespace(
            find_one=lambda q: job if clock.now >= eligible + 2 else None
        )
        traces = SimpleNamespace(find=lambda q: [{"agent_id": "quick"}])

    stages = []
    wait(
        {
            "db": DB(),
            "users": {"a": {"id": "owner"}},
            "output": tmp_path,
            "guard": SimpleNamespace(check=lambda: None),
        },
        "a",
        "source",
        stages.append,
    )
    assert [stage["kind"] for stage in stages] == [
        "natural_idle_extraction",
        "natural_unchanged_ticks",
    ]
    assert stages[0]["early_idle_observed"] is True
    assert len(stages[1]["fires"]) == 2


@pytest.mark.parametrize("kind", ["reflection", "compaction"])
def test_natural_maintenance_uses_real_scheduler_without_lowering_quality_guards(kind):
    configure = helpers()["natural_settings"]
    case = {"natural_maintenance": kind, "sources": [{"agent_id": "quick"}]}
    configured = configure([case])
    assert configured["MEMORY_EXTRACTION_ENABLED"] is False
    assert configured["NATIVE_MEMORY_SELF_EVOLVE_ENABLED"] is (kind == "reflection")
    assert configured["NATIVE_MEMORY_AUTO_COMPACT_ENABLED"] is (kind == "compaction")
    if kind == "compaction":
        assert configured["NATIVE_MEMORY_AUTO_COMPACT_THRESHOLD"] == 40
        assert configured["NATIVE_MEMORY_AUTO_COMPACT_MIN_INTERVAL_SECONDS"] == 900
    else:
        assert configured["NATIVE_MEMORY_SELF_EVOLVE_INTERVAL_SECONDS"] == 60
    with pytest.raises(ValueError):
        configure([case, {}])


def test_background_maintenance_phase_uses_the_actual_system_policy():
    from src.infra.memory.compaction_agent import _COMPACTION_SYSTEM_PROMPT
    from src.infra.memory.evolution.reflector import REFLECT_SYSTEM_PROMPT

    classify = helpers()["observed_phase"]
    for policy, expected in (
        (_COMPACTION_SYSTEM_PROMPT, "background_compaction"),
        (REFLECT_SYSTEM_PROMPT, "background_reflection"),
    ):
        assert classify([[SystemMessage(policy)]], "chat", "extraction") == expected
        assert (
            classify([[SystemMessage("Main policy"), HumanMessage(policy)]], "chat", "extraction")
            == "chat"
        )
    assert (
        classify([[SystemMessage(_COMPACTION_SYSTEM_PROMPT)]], "compaction", "extraction")
        == "compaction"
    )


@pytest.mark.parametrize("job", ["memory.compaction", "memory.evolution"])
def test_maintenance_receipts_identify_the_real_scheduled_job(tmp_path, job):
    import json
    from datetime import datetime, timezone
    from types import SimpleNamespace

    output = tmp_path / "fires.jsonl"
    helpers()["record_scheduler_fire"](
        SimpleNamespace(
            job_id=job,
            scheduled_run_time=datetime.now(timezone.utc),
            retval={"stored": 1},
            exception=None,
        ),
        output,
        "source",
    )
    receipt = json.loads(output.read_text())
    assert receipt["job_id"] == job and receipt["source_sha256"] == "source"


@pytest.mark.parametrize("kind", ["reflection", "compaction"])
def test_maintenance_observer_waits_for_real_completion_and_two_unchanged_ticks(tmp_path, kind):
    from datetime import datetime, timezone
    from types import SimpleNamespace

    wait = helpers()["wait_for_natural_maintenance"]
    clock = SimpleNamespace(now=1_800_000_000.0)
    start = clock.now
    phase = "background_" + kind
    job_id = "memory.evolution" if kind == "reflection" else "memory.compaction"

    def advance(seconds):
        clock.now += seconds

    wait.__globals__["time"] = SimpleNamespace(
        time=lambda: clock.now, monotonic=lambda: clock.now, sleep=advance
    )

    def rows(path):
        if path.name == "model-calls.jsonl":
            return (
                [{"event": "start", "phase": phase, "time": start + 60}]
                if clock.now >= start + 60
                else []
            )
        return [
            {
                "job_id": job_id,
                "scheduled_at": datetime.fromtimestamp(start + t, timezone.utc).isoformat(),
                "exception": None,
                "result": {"stored": int(t == 60), "triggered": int(t == 60)},
            }
            for t in (60, 120, 180)
            if clock.now >= start + max(t, 65)
        ]

    wait.__globals__["_rows"] = rows

    class DB:
        feedback = SimpleNamespace(
            find_one=lambda query: {"evolution_processed": clock.now >= start + 65}
        )
        native_memories = SimpleNamespace(
            count_documents=lambda query: (
                int(clock.now >= start + 65)
                if kind == "reflection"
                else 4
                if clock.now >= start + 65
                else 40
            )
        )

    stages = []
    wait(
        {
            "db": DB(),
            "users": {"a": {"id": "owner"}},
            "output": tmp_path,
            "guard": SimpleNamespace(check=lambda: None),
        },
        "a",
        stages.append,
        kind=kind,
        run_id="source",
        before_count=40,
        max_remaining=8,
    )
    assert clock.now == start + 180
    assert [stage["kind"] for stage in stages] == [
        "natural_" + kind,
        "natural_maintenance_unchanged_ticks",
    ]
    assert len(stages[1]["fires"]) == 2 and stages[1]["model_calls"] == 1


def test_frozen_natural_compaction_fixture_reaches_default_threshold_with_real_facts():
    import json

    from src.kernel.config.base import Settings

    suite = json.loads(
        (Path(__file__).parents[2] / "fixtures/memory_lifecycle/v14.json").read_text()
    )
    case = next(case for case in suite["cases"] if case.get("natural_maintenance") == "compaction")
    automatic = [
        seed
        for seed in case["seed_memories"]
        if seed["owner"] == "a" and seed["source"] == "auto_retained"
    ]
    assert (
        len(automatic)
        == Settings.model_fields["NATIVE_MEMORY_AUTO_COMPACT_THRESHOLD"].default
        == 40
    )
    assert len({seed["content"] for seed in automatic}) == 40
    assert case["max_remaining_auto_memories"] == 8
    protected = [seed for seed in case["seed_memories"] if seed.get("protected")]
    assert any(
        seed["owner"] == "a" and seed["source"] == "manual" and len(seed["content"]) > 1200
        for seed in protected
    )
    assert any(seed["owner"] == "b" for seed in protected)


def test_background_compaction_recognizes_canonical_policy_in_system_text_blocks():
    from src.infra.memory.compaction_agent import _COMPACTION_SYSTEM_PROMPT

    classify = helpers()["observed_phase"]
    content = [
        {"type": "text", "text": _COMPACTION_SYSTEM_PROMPT},
        {"type": "text", "text": "Additional runtime guidance."},
    ]
    assert classify([[SystemMessage(content)]], "chat", "extraction") == "background_compaction"
    assert (
        classify([[SystemMessage("Main policy"), HumanMessage(content)]], "chat", "extraction")
        == "chat"
    )
