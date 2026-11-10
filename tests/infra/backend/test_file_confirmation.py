from src.infra.backend.file_confirmation import (
    capture_file_confirmation,
    restore_file_confirmation,
)
from src.infra.backend.local import WorkspaceAliasBackend


def backend(machine="one"):
    return WorkspaceAliasBackend(user_id="owner", session_id="workspace", machine_id=machine)


def calls():
    return [
        {
            "id": "edit",
            "name": "edit_file",
            "args": {
                "file_path": "/workspace/workspace/note.txt",
                "old_string": "old",
                "new_string": "new",
            },
        }
    ]


async def test_approval_versions_cannot_move_to_another_machine_or_tool_call():
    source = backend()
    source._file_versions["note.txt"] = "observed-version"
    context = await capture_file_confirmation(source, calls())
    changed_machine = backend("two")
    assert not await restore_file_confirmation(changed_machine, calls(), context)
    assert changed_machine._file_versions == {}
    changed_call = calls()
    changed_call[0]["args"]["new_string"] = "different write"
    restored = backend()
    assert not await restore_file_confirmation(restored, changed_call, context)
    assert restored._file_versions == {}


async def test_execution_batch_cannot_restore_old_file_observations():
    source = backend()
    source._file_versions["note.txt"] = "observed-version"
    batch = calls() + [{"id": "exec", "name": "execute", "args": {"command": "true"}}]
    context = await capture_file_confirmation(source, batch)
    assert context["versions"] == {}
    restored = backend()
    assert await restore_file_confirmation(restored, batch, context)
    assert restored._file_versions == {}


async def test_approval_does_not_restore_unrelated_files_or_replace_newer_observations():
    source = backend()
    source._file_versions.update({"note.txt": "old-version", "other.txt": "other-version"})
    context = await capture_file_confirmation(source, calls())
    assert context["versions"] == {"note.txt": "old-version"}
    restored = backend()
    restored._file_versions["note.txt"] = "new-version"
    assert await restore_file_confirmation(restored, calls(), context)
    assert restored._file_versions == {"note.txt": "new-version"}
