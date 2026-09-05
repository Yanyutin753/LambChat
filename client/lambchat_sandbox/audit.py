"""JSONL 审计：daemon 的每次决定与执行都落一行，失败绝不阻断执行。

审计文件按会话分片：``{root}/{session_id}.jsonl``，每行一个 JSON 对象。
:meth:`Auditor.log` 自动补 ``ts``（UTC ISO-8601；event 自带 ts 时不覆盖）。

设计取舍：审计是旁路记录，不是执行链路的一环——任何 I/O 失败（目录不可写、
磁盘满、序列化异常）都静默吞掉。"记不下来"绝不能挡住"执行/回传"本身；
需要排查审计缺失时看 daemon 自身日志。
"""

from __future__ import annotations

import contextlib
import json
from datetime import UTC, datetime
from pathlib import Path


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


class Auditor:
    """按会话追加 JSONL 审计。构造只记 root，目录延迟到首次 log 时创建。"""

    def __init__(self, root: Path) -> None:
        self._root = Path(root)

    def log(self, session_id: str, event: dict) -> None:
        """追加一行事件到 ``{root}/{session_id}.jsonl``；任何失败静默吞掉。"""
        record = {"ts": _now_iso(), **event}  # 自动补 ts：event 自带时不覆盖
        with contextlib.suppress(Exception):
            self._root.mkdir(parents=True, exist_ok=True)
            with (self._root / f"{session_id}.jsonl").open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(record, ensure_ascii=False) + "\n")
