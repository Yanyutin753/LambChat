import json

from src.infra.backend.workspace_selection import selected_workspace_id


def test_workspace_requires_matching_explicit_machine():
    selection = json.dumps({"id": "local-" + "a" * 32, "machineId": "m1", "path": "/project"})
    assert (
        selected_workspace_id({"sandbox_workspace": selection, "sandbox_machine_id": "m1"})
        == "local-" + "a" * 32
    )
    assert (
        selected_workspace_id({"sandbox_workspace": selection, "sandbox_machine_id": "m2"}) is None
    )
    assert selected_workspace_id({"sandbox_workspace": selection}) is None


def test_workspace_rejects_paths_and_malformed_options():
    for selection in ["bad", "null", "[]", '{"id":"../../etc","machineId":"m1"}']:
        assert (
            selected_workspace_id({"sandbox_workspace": selection, "sandbox_machine_id": "m1"})
            is None
        )
