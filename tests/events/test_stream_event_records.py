import ast
import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURE_PATH = REPO_ROOT / "tests" / "events" / "stream_events.json"
PRESENTER_PATH = REPO_ROOT / "src" / "infra" / "writer" / "presenter_events.py"

NON_PRESENTER_STREAM_EVENTS = {
    "complete",
    "followup:questions",
    # ping 是 SSE 传输层心跳（dual_writer 产出、路由层转成 event: ping），
    # 不经过 presenter，但客户端会收到，须登记在 fixture 里
    "ping",
    "queue_update",
    "user:cancel",
}


def _presenter_event_names() -> set[str]:
    tree = ast.parse(PRESENTER_PATH.read_text())
    event_names: set[str] = set()

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if not isinstance(node.func, ast.Attribute) or node.func.attr != "_build_event":
            continue
        if not node.args:
            continue
        event_arg = node.args[0]
        if isinstance(event_arg, ast.Constant) and isinstance(event_arg.value, str):
            event_names.add(event_arg.value)

    return event_names


def test_stream_event_fixture_records_current_event_names() -> None:
    fixture = json.loads(FIXTURE_PATH.read_text())
    records = fixture["stream_events"]

    event_names = {record["event"] for record in records}

    assert event_names == _presenter_event_names() | NON_PRESENTER_STREAM_EVENTS


def test_stream_event_fixture_records_sse_shape_for_each_event() -> None:
    fixture = json.loads(FIXTURE_PATH.read_text())

    for record in fixture["stream_events"]:
        assert isinstance(record["event"], str)
        assert isinstance(record["data"], dict)
