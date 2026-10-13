from pathlib import Path

from src.kernel.config.base import Settings
from src.kernel.config.definitions import SETTING_DEFINITIONS


def test_session_execution_limit_defaults_are_consistent(monkeypatch):
    monkeypatch.delenv("SESSION_MAX_RUNS_PER_SESSION", raising=False)
    assert Settings(_env_file=None).SESSION_MAX_RUNS_PER_SESSION == 10000
    assert SETTING_DEFINITIONS["SESSION_MAX_RUNS_PER_SESSION"]["default"] == 10000
    for path in (".env.example", "docs/zh/env/session.md", "docs/en/env/session.md"):
        assert "SESSION_MAX_RUNS_PER_SESSION=10000" in Path(path).read_text()


def test_explicit_session_execution_limit_is_retained(monkeypatch):
    monkeypatch.setenv("SESSION_MAX_RUNS_PER_SESSION", "250")
    assert Settings(_env_file=None).SESSION_MAX_RUNS_PER_SESSION == 250
