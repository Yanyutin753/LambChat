"""Only server-created reveal indexes may establish historical file ownership."""

from copy import deepcopy
from importlib import import_module, util

import pytest

BASE_URL = "https://chat.example"
MAIN_KEY = "revealed_files/20261023_120000_ab123456_report.md"
ROOT_KEY = "revealed_projects/demo_ab123456"
IMAGE_KEY = ROOT_KEY + "/20261023_120000_cd123456_logo.png"


def _module():
    assert util.find_spec("scripts.backfill_generated_file_owners") is not None, (
        "Historical generated ownership migration is not implemented"
    )
    return import_module("scripts.backfill_generated_file_owners")


def _file_row(**changes):
    return {
        "_id": "reveal-1",
        "source": "reveal_file",
        "file_key": MAIN_KEY,
        "url": BASE_URL + "/api/upload/file/" + MAIN_KEY,
        "user_id": "owner",
        "session_id": "session-1",
        "original_path": "/workspace/report.md",
        "mime_type": "text/markdown",
        "file_size": 12,
        **changes,
    }


def _plan(rows, *, sessions=None, existing=None):
    return _module().build_plan(
        rows,
        {"session-1": "owner"} if sessions is None else sessions,
        [] if existing is None else existing,
        base_url=BASE_URL,
    )


def test_server_index_of_uploaded_main_file_establishes_only_its_exact_owner():
    rows = [_file_row()]
    original = deepcopy(rows)
    plan = _plan(rows)
    assert [(item["key"], item["uploaded_by"], item["generated_session_id"]) for item in plan] == [
        (MAIN_KEY, "owner", "session-1")
    ]
    assert rows == original


def test_project_manifest_grants_only_explicit_files_inside_its_uploaded_root():
    rows = [
        _file_row(
            source="reveal_project",
            file_key=ROOT_KEY,
            url=None,
            project_meta={
                "files": [
                    {"url": BASE_URL + "/api/upload/file/" + IMAGE_KEY, "size": 3},
                    {"url": "/api/upload/file/image/victim/secret.png", "size": 9},
                    {"url": "https://evil.example/api/upload/file/" + ROOT_KEY + "/other.png"},
                ]
            },
        )
    ]
    assert [item["key"] for item in _plan(rows)] == [IMAGE_KEY]


@pytest.mark.parametrize(
    "row",
    [
        _file_row(file_key=BASE_URL + "/api/upload/file/" + MAIN_KEY),
        _file_row(original_path=BASE_URL + "/api/upload/file/" + MAIN_KEY),
        _file_row(url="https://evil.example/api/upload/file/" + MAIN_KEY),
        _file_row(source="external_mcp"),
        _file_row(
            file_key="tool_binaries/legacy.png", url="/api/upload/file/tool_binaries/legacy.png"
        ),
        _file_row(file_key="cua_screenshots/owner/session-1/private.png"),
        _file_row(file_key="revealed_files/../image/victim/secret.png"),
    ],
)
def test_url_echoes_private_captures_and_unidentified_tool_results_are_not_evidence(row):
    assert _plan([row]) == []


@pytest.mark.parametrize("sessions", [{}, {"session-1": "victim"}])
def test_missing_or_differently_owned_source_session_never_grants_ownership(sessions):
    assert _plan([_file_row()], sessions=sessions) == []


def test_conflicting_server_indexes_never_assign_one_object_to_two_accounts():
    other = _file_row(_id="reveal-2", user_id="other", session_id="session-2")
    assert _plan([_file_row(), other], sessions={"session-1": "owner", "session-2": "other"}) == []


@pytest.mark.parametrize(
    "record",
    [
        {"key": MAIN_KEY, "uploaded_by": "victim"},
        {"key": MAIN_KEY, "uploaded_by": "owner"},
        {"key": MAIN_KEY, "uploaded_by": "owner", "deleting_at": "pending"},
    ],
)
def test_existing_ownership_or_cleanup_records_are_never_overwritten(record):
    original = deepcopy(record)
    assert _plan([_file_row()], existing=[record]) == []
    assert record == original


def test_html_references_do_not_grant_ownership_to_unregistered_resources():
    row = _file_row(content='<img src="/api/upload/file/revealed_files/unknown.png">')
    assert [item["key"] for item in _plan([row])] == [MAIN_KEY]


def test_main_url_must_agree_with_the_server_assigned_storage_key():
    assert _plan([_file_row(url="/api/upload/file/image/victim/secret.png")]) == []


async def test_default_dry_run_cannot_write_or_initialize_indexes():
    class ReadOnlyRecords:
        async def update_one(self, *_args, **_kwargs):
            pytest.fail("dry-run attempted a database write")

        async def list_indexes(self):
            pytest.fail("dry-run attempted index initialization")

    class Storage:
        async def get_size(self, key):
            return 12 if key == MAIN_KEY else None

    report = await _module().write_plan(ReadOnlyRecords(), Storage(), _plan([_file_row()]))
    assert report == {"eligible": 1, "inserted": 0, "already_present": 0, "unavailable": 0}


async def test_apply_requires_the_unique_key_index_before_any_write():
    class Records:
        async def list_indexes(self):
            async def indexes():
                yield {"key": {"_id": 1}, "unique": True}

            return indexes()

        async def update_one(self, *_args, **_kwargs):
            pytest.fail("migration wrote without the unique key index")

    with pytest.raises(RuntimeError, match="unique.*key"):
        await _module().write_plan(Records(), None, _plan([_file_row()]), apply=True)
