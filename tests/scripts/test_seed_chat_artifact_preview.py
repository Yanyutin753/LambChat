from datetime import datetime, timezone

from scripts.seed_chat_artifact_preview import build_preview


def test_artifact_preview_only_adds_owned_chats_and_matching_downloadable_files():
    records, files = build_preview("owner", datetime(2026, 10, 12, tzinfo=timezone.utc))
    assert set(records) == {"sessions", "traces", "file_records"}
    assert len(records["sessions"]) == len(records["traces"]) == 4
    assert all(doc["preview_owner"] == "owner" for docs in records.values() for doc in docs)
    assert [
        sum(e["event_type"] == "artifact:result" for e in t["events"]) for t in records["traces"]
    ] == [1, 3, 6, 3]
    assert all(t["events"][-1]["event_type"] == "done" for t in records["traces"])
    assert {t["session_id"] for t in records["traces"]} == {
        s["session_id"] for s in records["sessions"]
    }
    for record in records["file_records"]:
        assert record["uploaded_by"] == "owner"
        assert len(files[record["key"]]) == record["size"]
    assert len({r["hash"] for r in records["file_records"]}) == len(records["file_records"])
    other, _ = build_preview("other", datetime(2026, 10, 12, tzinfo=timezone.utc))
    assert {str(s["_id"]) for s in records["sessions"]}.isdisjoint(
        str(s["_id"]) for s in other["sessions"]
    )


def test_mixed_preview_contains_a_renderable_project_and_two_files():
    records, _ = build_preview("owner", datetime(2026, 10, 12, tzinfo=timezone.utc))
    artifacts = [
        e["data"]["artifact"]
        for e in records["traces"][-1]["events"]
        if e["event_type"] == "artifact:result"
    ]
    assert [a["kind"] for a in artifacts] == ["file", "file", "project"]
    project = artifacts[-1]["preview"]["project"]
    assert project["entry"] in project["files"]
    assert project["fileCount"] == len(project["files"]) == 2
