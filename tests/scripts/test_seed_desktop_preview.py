from datetime import datetime, timezone

import pytest

from scripts.seed_desktop_preview import build_records, validate_target


def test_preview_records_are_repeatable_owned_and_inert():
    now = datetime(2026, 9, 30, tzinfo=timezone.utc)
    records = build_records("owner", now)
    assert records == build_records("owner", now)
    assert len(records["sessions"]) >= 25
    for collection, docs in records.items():
        assert len({str(d["_id"]) for d in docs}) == len(docs), collection
        assert all(d["preview_owner"] == "owner" for d in docs)
    for name in ("model_configs", "user_mcp_servers", "user_channel_configs", "scheduled_tasks"):
        assert all(not d["enabled"] for d in records[name])
    assert all(d["status"] == "paused" for d in records["scheduled_tasks"])
    assert all(not d["is_active"] for d in records["users"])
    assert "system_settings" not in records
    assert all(d.get("api_key") is None for d in records["model_configs"])
    sessions = {str(d["_id"]) for d in records["sessions"]}
    assert all(d["session_id"] in sessions for d in records["traces"])


@pytest.mark.parametrize(
    "uri,db,user",
    [
        ("mongodb://production.example:27017", "agent_state", "desktop_dev"),
        ("mongodb://localhost:27017", "production", "desktop_dev"),
        ("mongodb://localhost:27017", "agent_state", "admin"),
        ("mongodb://localhost:27017,production.example:27017", "agent_state", "desktop_dev"),
    ],
)
def test_rejects_nonlocal_or_unexpected_destinations(uri, db, user):
    with pytest.raises(ValueError):
        validate_target(uri, db, user)


def test_local_files_have_matching_hashes_and_records():
    from hashlib import sha256

    from scripts.seed_desktop_preview import preview_files

    now = datetime(2026, 9, 30, tzinfo=timezone.utc)
    records = build_records("owner", now)
    files = preview_files("owner")
    assert len(files) == 30
    assert len(records["revealed_files"]) == len(records["file_records"]) == len(files)
    for record in records["file_records"]:
        content = files[record["key"]]
        assert record["hash"] == sha256(content).hexdigest()
        assert record["size"] == len(content)


def test_seed_refuses_collision_before_writing_any_collection():
    from unittest.mock import MagicMock

    from scripts.seed_desktop_preview import seed

    db = MagicMock()
    db.__getitem__.return_value.find_one.side_effect = [None, {"preview_owner": "another-user"}]
    with pytest.raises(ValueError, match="collision"):
        seed(db, "owner", {"sessions": [{"_id": "a"}, {"_id": "b"}]})
    db.__getitem__.return_value.update_one.assert_not_called()


def test_seed_preserves_existing_values_on_repeat_runs():
    from unittest.mock import MagicMock

    from scripts.seed_desktop_preview import seed

    db = MagicMock()
    db.__getitem__.return_value.find_one.return_value = {"preview_owner": "owner"}
    doc = {"_id": "a", "preview_owner": "owner", "name": "Example"}
    for _ in range(2):
        assert seed(db, "owner", {"sessions": [doc]}) == {"sessions": 1}
    assert db.__getitem__.return_value.update_one.call_count == 2
    db.__getitem__.return_value.update_one.assert_called_with(
        {"_id": "a", "preview_owner": "owner"}, {"$setOnInsert": doc}, upsert=True
    )


def test_preview_memories_cover_supported_memory_types():
    from src.infra.memory.client.types import MemoryType

    memories = build_records("owner", datetime(2026, 9, 30, tzinfo=timezone.utc))["native_memories"]
    assert {memory["memory_type"] for memory in memories} == {kind.value for kind in MemoryType}


def test_revealed_files_form_six_named_groups_with_consistent_trace_links():
    from collections import Counter

    records = build_records("owner", datetime(2026, 9, 30, tzinfo=timezone.utc))
    files = records["revealed_files"]
    groups = Counter(file["session_id"] for file in files)
    assert len(groups) == 6
    assert set(groups.values()) == {5}
    sessions = {session["session_id"]: session for session in records["sessions"]}
    traces = {trace["trace_id"]: trace for trace in records["traces"]}
    for file in files:
        session = sessions[file["session_id"]]
        assert session["name"]
        assert file["project_id"] == session["metadata"]["project_id"]
        assert traces[file["trace_id"]]["session_id"] == file["session_id"]
