"""Auditor：按会话追加 JSONL 审计，自动补 ts，失败静默绝不阻断执行。"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from lambchat_sandbox.audit import Auditor


def _read_lines(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines()]


def test_log_appends_two_jsonl_records_with_ts(tmp_path):
    auditor = Auditor(tmp_path)
    auditor.log("s1", {"event": "received", "command": "echo hi"})
    auditor.log("s1", {"event": "executed", "exit_code": 0})

    audit_file = tmp_path / "s1.jsonl"
    records = _read_lines(audit_file)
    assert len(records) == 2
    assert [r["event"] for r in records] == ["received", "executed"]
    assert records[0]["command"] == "echo hi"
    assert records[1]["exit_code"] == 0
    for record in records:
        # 自动补 ts：存在且为可解析的 ISO-8601 时间戳
        assert "ts" in record
        assert datetime.fromisoformat(record["ts"]).tzinfo == UTC


def test_log_does_not_overwrite_explicit_ts(tmp_path):
    # "自动补"：event 自带 ts 时不覆盖
    explicit = "2026-09-05T00:00:00+00:00"
    Auditor(tmp_path).log("s1", {"event": "custom", "ts": explicit})
    assert _read_lines(tmp_path / "s1.jsonl")[0]["ts"] == explicit


def test_log_separates_sessions_into_per_session_files(tmp_path):
    auditor = Auditor(tmp_path)
    auditor.log("s1", {"event": "a"})
    auditor.log("s2", {"event": "b"})
    assert _read_lines(tmp_path / "s1.jsonl")[0]["event"] == "a"
    assert _read_lines(tmp_path / "s2.jsonl")[0]["event"] == "b"


def test_log_creates_missing_root_directories(tmp_path):
    root = tmp_path / "deep" / "audit"
    Auditor(root).log("s1", {"event": "received"})
    assert (root / "s1.jsonl").exists()


def test_log_swallows_failures_when_root_is_a_file(tmp_path):
    # root 被同名普通文件占位：mkdir 必然失败，审计不得抛出阻断执行
    blocker = tmp_path / "blocker"
    blocker.write_text("not a directory")
    Auditor(blocker).log("s1", {"event": "received"})  # 不抛即通过


def test_log_swallows_failures_on_unwritable_directory(tmp_path):
    root = tmp_path / "ro"
    root.mkdir()
    root.chmod(0o500)  # 去掉写权限（root 运行时 chmod 不生效，用文件占位测试兜底）
    try:
        Auditor(root).log("s1", {"event": "received"})
    finally:
        root.chmod(0o700)


def test_log_failure_does_not_break_subsequent_logging(tmp_path):
    blocker = tmp_path / "blocker"
    blocker.write_text("not a directory")
    broken = Auditor(blocker)
    good = Auditor(tmp_path / "fine")
    broken.log("s1", {"event": "doomed"})  # 失败被吞
    good.log("s1", {"event": "received"})  # 后续审计照常工作
    assert _read_lines(tmp_path / "fine" / "s1.jsonl")[0]["event"] == "received"
