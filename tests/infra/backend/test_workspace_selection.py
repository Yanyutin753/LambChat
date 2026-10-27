import json

import pytest

from src.infra.backend.workspace_selection import selected_workspace_id
from src.kernel.errors import AppError


def test_workspace_requires_matching_explicit_machine():
    selection = json.dumps({"id": "local-" + "a" * 32, "machineId": "m1", "path": "/project"})
    assert (
        selected_workspace_id({"sandbox_workspace": selection, "sandbox_machine_id": "m1"})
        == "local-" + "a" * 32
    )
    with pytest.raises(AppError):
        selected_workspace_id({"sandbox_workspace": selection, "sandbox_machine_id": "m2"})
    with pytest.raises(AppError):
        selected_workspace_id({"sandbox_workspace": selection})


def test_workspace_rejects_paths_and_malformed_options():
    for selection in ["bad", "null", "[]", '{"id":"../../etc","machineId":"m1"}']:
        with pytest.raises(AppError):
            selected_workspace_id({"sandbox_workspace": selection, "sandbox_machine_id": "m1"})


def test_only_absent_or_explicitly_cleared_selection_uses_session_directory():
    for value in [None, ""]:
        assert selected_workspace_id({"sandbox_workspace": value}) is None
    for value in [False, 0, {}, [], "{}"]:
        with pytest.raises(AppError):
            selected_workspace_id({"sandbox_workspace": value})
