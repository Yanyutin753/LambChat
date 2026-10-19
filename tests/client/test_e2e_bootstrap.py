import importlib.util
import sys
from pathlib import Path
from unittest.mock import Mock

import pytest

ROOT = Path(__file__).parents[2]


def test_e2e_bootstrap_uses_configured_server_host_and_port() -> None:
    source = (ROOT / "scripts/e2e_local_sandbox.py").read_text(encoding="utf-8")

    assert "parsed = urlsplit(SERVER)" in source
    assert '"--host",\n                parsed.hostname' in source
    assert '"--port",\n                str(port)' in source


def test_e2e_stops_its_daemon_when_a_battery_raises(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location(
        "e2e_local_sandbox_cleanup", ROOT / "scripts/e2e_local_sandbox.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    daemon = Mock()
    daemon.poll.return_value = None

    async def failed_battery(*args):
        raise RuntimeError("battery failed")

    monkeypatch.setattr(sys, "argv", ["e2e_local_sandbox.py", "--selected-workspace-only"])
    monkeypatch.setattr(module, "ensure_backend", lambda: None)
    monkeypatch.setattr(module, "mint_pat", lambda *args: ("test-pat", "test-jwt"))
    monkeypatch.setattr(module, "http_json", lambda *args, **kwargs: (200, {"id": "test-user"}))
    monkeypatch.setattr(module, "spawn_daemon", lambda *args: daemon)
    monkeypatch.setattr(module, "selected_workspace_battery", failed_battery)
    monkeypatch.setattr(module, "cleanup_user", Mock())
    monkeypatch.setattr(module, "WORKSPACE_ROOT", tmp_path)

    with pytest.raises(RuntimeError, match="battery failed"):
        module.main()

    daemon.terminate.assert_called_once()
    daemon.wait.assert_called_once_with(timeout=10)
