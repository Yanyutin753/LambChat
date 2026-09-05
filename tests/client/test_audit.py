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


def test_log_silently_drops_illegal_session_ids(tmp_path):
    # sid 白名单：与 executor.map_workspace 对 sid 的防线同级——含 / 或 ..
    # 的 sid 会写出 audit root 之外，必须静默丢弃（不抛、不落盘）
    root = tmp_path / "audit"
    sid_absolute = str(tmp_path / "escaped")  # 绝对路径整体替换 root
    for sid in ["../evil", "a/b", sid_absolute]:
        Auditor(root).log(sid, {"event": "received"})  # 不抛即通过

    assert not (root / "evil.jsonl").exists()  # ../evil 不落 root 内
    assert not (tmp_path / "evil.jsonl").exists()  # 也不落 root 外（上溯）
    assert not Path(sid_absolute + ".jsonl").exists()  # 绝对路径不落
    assert not list(root.rglob("*.jsonl"))  # root 内一个文件都不落


def test_log_accepts_whitelisted_session_id_characters(tmp_path):
    # 白名单字符集（字母/数字/._-）内的合法 sid 照常追加
    sid = "sess.1-x_9"
    Auditor(tmp_path).log(sid, {"event": "received"})
    assert _read_lines(tmp_path / f"{sid}.jsonl")[0]["event"] == "received"


def test_log_swallows_non_dict_event(tmp_path):
    # 构造容错：record 合并纳入 suppress——非 dict 的 event 不抛、不落盘
    Auditor(tmp_path).log("s1", ["not", "a", "dict"])  # 不抛即通过
    assert not list(tmp_path.rglob("*.jsonl"))
