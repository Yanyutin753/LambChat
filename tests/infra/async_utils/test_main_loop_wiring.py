"""源码接线校验：主循环登记必须出现在两个进程入口。

本地沙箱同步桥接的跨循环修复依赖 lifespan / arq worker startup 显式登记
主事件循环（loop_bridge.set_main_loop）；漏掉任何一处，对应进程里的同步
文件操作就会退回 asyncio.run 临时循环，重新引入 redis 连接池跨循环污染
（2026-09-06 生产事故）。源码扫描锁死接线不被顺手删掉。
"""

from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]


def test_api_lifespan_registers_main_loop():
    main_py = _REPO_ROOT / "src" / "api" / "main.py"
    text = main_py.read_text(encoding="utf-8")
    lifespan_body = text.split("async def lifespan", 1)[1].split("\nasync def", 1)[0]
    assert "loop_bridge.set_main_loop(asyncio.get_running_loop())" in lifespan_body
    assert "loop_bridge.clear_main_loop()" in lifespan_body


def test_arq_worker_registers_main_loop():
    worker_py = _REPO_ROOT / "src" / "infra" / "task" / "arq_worker.py"
    text = worker_py.read_text(encoding="utf-8")
    startup_body = text.split("async def worker_startup", 1)[1].split("\nasync def", 1)[0]
    shutdown_body = text.split("async def worker_shutdown", 1)[1].split("\ndef ", 1)[0]
    assert "loop_bridge.set_main_loop(asyncio.get_running_loop())" in startup_body
    assert "loop_bridge.clear_main_loop()" in shutdown_body


def test_local_compat_delegates_to_loop_bridge():
    compat_py = _REPO_ROOT / "src" / "infra" / "backend" / "_local_compat.py"
    text = compat_py.read_text(encoding="utf-8")
    body = text.split("def _run_coro_sync", 1)[1]
    assert "loop_bridge.run_coro_sync(coro)" in body
    # 旧实现特征（asyncio.run 直跑）不应再出现在函数体里
    assert "return asyncio.run(coro)" not in body
