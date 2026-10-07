"""守门：飞书共享 WS loop 首次创建含线程等待与锁，不得在事件循环线程上执行。

`_ensure_feishu_ws_loop` 内部有 `ready.wait(timeout=5)` 与同步锁等待，
冷启动时还要等 `import lark_oapi.ws.client`——若在 async 上下文裸调用，
会卡住整个事件循环最多 5 秒。必须经 run_blocking_io 卸载。
"""

from pathlib import Path

_SOURCE = (
    Path(__file__).resolve().parents[2] / "src" / "infra" / "channel" / "feishu" / "channel.py"
).read_text(encoding="utf-8")


def test_start_offloads_shared_ws_loop_creation() -> None:
    assert "await run_blocking_io(_ensure_feishu_ws_loop)" in _SOURCE


def test_shared_ws_loop_is_never_created_inline_on_event_loop() -> None:
    assert "= _ensure_feishu_ws_loop()" not in _SOURCE
