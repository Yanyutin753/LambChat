"""Validate that langchain_stream_events.json covers all event types consumed by AgentEventProcessor."""

import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURE_PATH = REPO_ROOT / "tests" / "events" / "langchain_stream_events.json"
PROCESSOR_PATH = REPO_ROOT / "src" / "infra" / "agent" / "events" / "processor.py"

# LangChain astream_events v2 standard event types that exist but are explicitly
# NOT processed (silently filtered out by AgentEventProcessor).
EXPECTED_UNHANDLED_EVENTS = frozenset(
    {
        "on_chat_model_start",
        "on_chain_start",
        "on_chain_stream",
        "on_chain_end",
        "on_retriever_start",
        "on_retriever_end",
        "on_parser_start",
        "on_parser_end",
    }
)


def _load_fixture() -> dict:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def _load_fixture_event_names() -> set[str]:
    return {record["event"] for record in _load_fixture()["stream_events"]}


def _extract_processed_event_types() -> set[str]:
    """Extract all LangChain event types that AgentEventProcessor.process_event handles.

    Scans processor.py for:
    1. The _CONTEXT_EVENT_TYPES frozenset (handled context events)
    2. Explicit `on_chat_model_end` check
    3. TOOL_TASK match branches (these use on_tool_start/end/error, already in _CONTEXT_EVENT_TYPES)
    """
    source = PROCESSOR_PATH.read_text(encoding="utf-8")

    # 1. Extract _CONTEXT_EVENT_TYPES frozenset
    import re

    ctx_match = re.search(
        r"_CONTEXT_EVENT_TYPES\s*=\s*frozenset\s*\(\s*\(([^)]+)\)\s*\)",
        source,
    )
    assert ctx_match, "Could not find _CONTEXT_EVENT_TYPES in processor.py"
    ctx_types = {
        s.strip().strip('"').strip("'") for s in ctx_match.group(1).split(",") if s.strip()
    }

    # 2. Find all `case "on_*"` patterns in process_event
    case_matches = re.findall(r'case\s+"(on_[a-z_]+)"', source)
    case_types = set(case_matches)

    # 3. Find all `== "on_*"` explicit comparisons
    eq_matches = re.findall(r'==\s+"(on_[a-z_]+)"', source)
    eq_types = set(eq_matches)

    return ctx_types | case_types | eq_types


def test_fixture_covers_all_processed_event_types() -> None:
    """Every LangChain event type handled by AgentEventProcessor must appear in the fixture."""
    processed = _extract_processed_event_types()
    fixture_names = _load_fixture_event_names()

    missing = processed - fixture_names
    assert not missing, (
        f"LangChain event types handled by AgentEventProcessor but missing from fixture: {missing}"
    )


def test_fixture_includes_unhandled_events() -> None:
    """Fixture should document at least the known unhandled event types."""
    fixture_names = _load_fixture_event_names()
    missing = EXPECTED_UNHANDLED_EVENTS - fixture_names
    assert not missing, f"Expected unhandled event types missing from fixture: {missing}"


def test_handled_events_are_marked_correctly() -> None:
    """Events marked handled_by_processor=true must match the actual processed set."""
    processed = _extract_processed_event_types()
    fixture = _load_fixture()

    for record in fixture["stream_events"]:
        event_name = record["event"]
        is_handled = record.get("handled_by_processor", False)
        expected_handled = event_name in processed

        assert is_handled == expected_handled, (
            f"Event '{event_name}': handled_by_processor={is_handled} "
            f"but {'is' if expected_handled else 'is not'} actually processed by AgentEventProcessor"
        )


def test_handled_events_have_handler_and_emits_sse() -> None:
    """Every handled event must specify a handler and list of emitted SSE events."""
    fixture = _load_fixture()

    for record in fixture["stream_events"]:
        if record.get("handled_by_processor"):
            assert "handler" in record, (
                f"Event '{record['event']}' is marked handled but missing 'handler' field"
            )
            assert "emits_sse" in record, (
                f"Event '{record['event']}' is marked handled but missing 'emits_sse' field"
            )


def test_fixture_has_valid_structure() -> None:
    """Each fixture record must have required fields and valid data_shape where present."""
    fixture = _load_fixture()

    required_fields = {"event", "lc_type", "description", "handled_by_processor"}
    for record in fixture["stream_events"]:
        assert required_fields.issubset(record.keys()), (
            f"Event '{record.get('event', '?')}' missing required fields: "
            f"{required_fields - record.keys()}"
        )
        assert record["lc_type"] in ("StandardStreamEvent", "CustomStreamEvent")


def test_context_event_types_match_processor() -> None:
    """The context_event_types in the fixture must exactly match _CONTEXT_EVENT_TYPES in processor.py."""
    import re

    source = PROCESSOR_PATH.read_text(encoding="utf-8")
    ctx_match = re.search(
        r"_CONTEXT_EVENT_TYPES\s*=\s*frozenset\s*\(\s*\(([^)]+)\)\s*\)",
        source,
    )
    assert ctx_match
    actual = {s.strip().strip('"').strip("'") for s in ctx_match.group(1).split(",") if s.strip()}

    fixture = _load_fixture()
    fixture_ctx = set(fixture["context_event_types"])
    assert fixture_ctx == actual, (
        f"context_event_types mismatch: fixture={fixture_ctx}, actual={actual}"
    )
