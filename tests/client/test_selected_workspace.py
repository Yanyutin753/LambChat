import json

import pytest

from lambchat_sandbox.executor import Executor, ExecutorError, map_workspace


def test_selected_directory_is_used_for_commands_and_mapping(tmp_path):
    root = tmp_path / "workspaces"
    selected = tmp_path / "project"
    selected.mkdir()
    bindings = root / ".selected"
    bindings.mkdir(parents=True)
    key = "local-" + "a" * 32
    (bindings / f"{key}.json").write_text(json.dumps(str(selected)))
    assert map_workspace(f"/workspace/.selected/{key}", root) == selected
    result = Executor(root).execute("echo hello > result.txt", f"/workspace/.selected/{key}", 5)
    assert result["exit_code"] == 0
    assert (selected / "result.txt").read_text().strip() == "hello"


@pytest.mark.parametrize("value", [None, "missing", "relative/path"])
def test_selected_directory_fails_closed_when_binding_is_unavailable(tmp_path, value):
    bindings = tmp_path / ".selected"
    bindings.mkdir()
    key = "local-" + "b" * 32
    if value is not None:
        (bindings / f"{key}.json").write_text(json.dumps(value))
    with pytest.raises(ExecutorError):
        map_workspace(f"/workspace/.selected/{key}", tmp_path)
