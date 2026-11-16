import importlib.util
import json
import os
import subprocess
from pathlib import Path

import pytest


@pytest.fixture
def collector():
    path = Path(__file__).resolve().parents[3] / "k8s/scripts/incident_evidence.py"
    assert path.exists(), "incident collection must survive host restarts"
    spec = importlib.util.spec_from_file_location("incident_evidence", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_healthy_services_do_not_collect_diagnostics(collector, monkeypatch, tmp_path):
    monkeypatch.setattr(collector, "probe", lambda port: None)
    monkeypatch.setattr(collector.subprocess, "run", lambda *a, **k: pytest.fail("healthy host"))
    assert collector.collect(tmp_path) is None
    assert list(tmp_path.iterdir()) == []


def test_redis_failure_captures_bounded_commands_despite_timeout(collector, monkeypatch, tmp_path):
    monkeypatch.setattr(collector, "probe", lambda port: "refused" if port == 6379 else None)
    calls = []

    def run(command, **kwargs):
        calls.append(command)
        assert kwargs["timeout"] == 8
        assert kwargs["check"] is False
        if len(calls) == 1:
            raise subprocess.TimeoutExpired(command, 8)
        return subprocess.CompletedProcess(command, 0, "evidence", "")

    monkeypatch.setattr(collector.subprocess, "run", run)
    path = collector.collect(tmp_path)
    report = json.loads(path.read_text())
    assert report["failed_probes"] == {"6379": "refused"}
    assert report["commands"][0]["error"] == "timeout"
    assert report["commands"][-1]["stdout"] == "evidence"
    assert len(calls) == len(collector.COMMANDS)
    assert path.stat().st_mode & 0o777 == 0o600
    assert tmp_path.stat().st_mode & 0o777 == 0o700


def test_repeated_failure_is_cooled_down_and_retention_preserves_other_files(
    collector, monkeypatch, tmp_path
):
    monkeypatch.setattr(collector, "probe", lambda port: "refused")
    monkeypatch.setattr(collector.time, "time", lambda: 1000)
    monkeypatch.setattr(
        collector.subprocess,
        "run",
        lambda command, **k: subprocess.CompletedProcess(command, 0, "", ""),
    )
    unrelated = tmp_path / "manual-evidence.json"
    unrelated.write_text("keep")
    for i in range(20):
        path = tmp_path / f"incident-{i}.json"
        path.write_text("{}")
        os.utime(path, (i, i))
    newest = collector.collect(tmp_path)
    assert newest.exists()
    assert len(list(tmp_path.glob("incident-*.json"))) == 20
    assert not (tmp_path / "incident-0.json").exists()
    assert unrelated.read_text() == "keep"
    monkeypatch.setattr(collector.subprocess, "run", lambda *a, **k: pytest.fail("cooldown"))
    assert collector.collect(tmp_path) is None


def test_probe_has_a_socket_deadline(collector, monkeypatch):
    def connect(address, timeout):
        assert address == ("127.0.0.1", 27017)
        assert timeout == 3
        raise TimeoutError("timed out")

    monkeypatch.setattr(collector.socket, "create_connection", connect)
    assert "timed out" in collector.probe(27017)


def test_missing_diagnostic_and_large_output_are_explicit(collector, monkeypatch, tmp_path):
    monkeypatch.setattr(collector, "probe", lambda port: "refused")

    def run(command, **kwargs):
        if command == collector.COMMANDS[0]:
            raise FileNotFoundError("unavailable")
        return subprocess.CompletedProcess(command, 1, "x" * 524289, "failed")

    monkeypatch.setattr(collector.subprocess, "run", run)
    report = json.loads(collector.collect(tmp_path).read_text())
    assert report["commands"][0]["error"] == "unavailable"
    assert report["commands"][-1]["returncode"] == 1
    assert len(report["commands"][-1]["stdout"]) == 524288
    assert report["commands"][-1]["truncated"]


def test_evidence_directory_cannot_redirect_through_symlink(collector, monkeypatch, tmp_path):
    monkeypatch.setattr(collector, "probe", lambda port: "refused")
    destination = tmp_path / "private"
    destination.mkdir()
    link = tmp_path / "link"
    link.symlink_to(destination, target_is_directory=True)
    with pytest.raises(ValueError, match="symlink"):
        collector.collect(link)
    assert list(destination.iterdir()) == []
