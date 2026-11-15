"""Native smoke must fail when cleanup fails after a successful GUI oracle."""

import importlib.util
import json
from pathlib import Path


def test_cleanup_error_does_not_publish_success(tmp_path, monkeypatch):
    path = Path(__file__).resolve().parents[2] / "client/scripts/smoke-cua-windows.py"
    spec = importlib.util.spec_from_file_location("windows_cua_smoke", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    daemon = tmp_path / "daemon.exe"
    daemon.touch()
    report_dir = tmp_path / "report"

    async def verify(daemon, directory, report):
        report["success"] = True
        raise PermissionError("cleanup failed")

    monkeypatch.setattr(module, "verify", verify)
    monkeypatch.setattr(module.sys, "platform", "win32")
    monkeypatch.setattr(
        module.sys, "argv", [str(path), "--daemon", str(daemon), "--report-dir", str(report_dir)]
    )
    assert module.main() == 1
    report = json.loads((report_dir / "report.json").read_text())
    assert report["success"] is False
    assert report["error"] == "PermissionError: cleanup failed"
