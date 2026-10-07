"""守门：技能 ZIP 解析是秒级 CPU 活，必须在慢道（run_long_blocking_io）执行。

快道只有 8 线程且默认 30s 超时，承载密钥加解密、pubsub 等关键路径；
大 zip 解析占用快道会拖慢全站关键操作。
"""

from pathlib import Path

_SOURCE = (Path(__file__).resolve().parents[3] / "src" / "api" / "routes" / "skill.py").read_text(
    encoding="utf-8"
)


def test_zip_parse_never_occupies_fast_lane() -> None:
    assert "run_blocking_io(_parse_zip" not in _SOURCE


def test_zip_parse_runs_on_slow_lane() -> None:
    assert _SOURCE.count("run_long_blocking_io(_parse_zip") == 2
