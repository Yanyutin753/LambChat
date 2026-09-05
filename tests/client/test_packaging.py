"""daemon 打包管线结构测试：纯文件断言（前端 ``*Source.test.ts`` 思路的 pytest 版）。

不执行真实打包，只锁定打包管线的结构契约：
- ``client/pyinstaller.spec`` 必须以 ``client/lambchat_sandbox/__main__.py`` 为入口
  （与 ``python -m lambchat_sandbox`` 等价）、onefile、产物名 ``lambchat-daemon``；
- ``client/scripts/build-daemon.sh`` 必须探测 host triple（rustc 优先、uname -m 映射兜底）
  并把产物落位到 Tauri sidecar 约定路径；
- Makefile 必须暴露 ``client-build-daemon`` 目标驱动该脚本。
"""

from pathlib import Path


def _source(path: str) -> str:
    """读文件原文；文件缺失时返回空串，让断言（而非收集错误）暴露缺失。"""
    p = Path(path)
    return p.read_text(encoding="utf-8") if p.exists() else ""


def test_spec_bundles_daemon_entry_as_onefile_named_lambchat_daemon() -> None:
    spec = _source("client/pyinstaller.spec")

    # 入口与 python -m lambchat_sandbox 等价
    assert "client/lambchat_sandbox/__main__.py" in spec
    # 产物名与控制台形态（sidecar 是无 GUI 的常驻进程）
    assert 'name="lambchat-daemon"' in spec
    assert "console=True" in spec
    # onefile 判据：EXE 吸收 binaries/datas，且没有 COLLECT（onedir 才有）
    assert "a.binaries" in spec
    assert "a.datas" in spec
    assert "COLLECT(" not in spec
    # 瘦身契约：排除 httpx[cli]/anyio 可选依赖链（rich→pygments→PIL→numpy、
    # click、zstandard、uvloop 等，均为条件导入，daemon 运行路径用不到）
    for heavy in ("numpy", "PIL", "rich", "pygments", "click", "zstandard", "uvloop", "yaml"):
        assert f'"{heavy}"' in spec, f"spec excludes 应包含 {heavy}"


def test_build_script_detects_host_triple_and_targets_sidecar_path() -> None:
    script = _source("client/scripts/build-daemon.sh")

    # triple 探测：rustc 优先，无 rustc 时 uname -m 映射到 linux-gnu triple
    assert "rustc -vV" in script
    assert "uname -m" in script
    assert "x86_64-unknown-linux-gnu" in script
    assert "aarch64-unknown-linux-gnu" in script
    # 打包调用链与产物落点
    assert "client/pyinstaller.spec" in script
    assert "--distpath client/dist" in script
    assert "frontend/src-tauri/binaries/lambchat-daemon-" in script


def test_makefile_exposes_client_build_daemon_target() -> None:
    makefile = _source("Makefile")

    assert "\nclient-build-daemon:" in makefile
    assert "client/scripts/build-daemon.sh" in makefile
