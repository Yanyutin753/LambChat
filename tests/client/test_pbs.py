"""pbs.ensure_runtime：内嵌 python-build-standalone 解压 / shim / 幂等 / 回退。

测试策略：``tarfile`` 现场构造小归档（假解释器是 shell 脚本），resources /
install_root 全部落 tmp_path，绝不碰真实 ``~/.lambchat``：

- 解压：install_dir 出现归档内容 + 幂等标记文件；shim（``bin/python3``）存在
  且可执行；
- PBS 布局（``python/bin/python3``）与扁平布局（``bin/python3``）都认；
- shim 语义（POSIX）：exec wrapper 脚本——执行 shim 时假解释器的 ``$0`` 是
  **归档里的真实解释器路径**（真实 PBS 下等价于 ``sys.executable`` 命中
  ``~/.lambchat/python/<tag>/`` 而非 shim 自身路径；符号链接做不到这一点）；
- 幂等：首次解压后删掉 tar.gz 再调一次，不重解压（标记文件为门）且仍返回
  bin 目录；重复调用不炸；
- Windows 分支（``platform._sys_platform`` 注入 win32）：shim 是 ``python3.exe``
  **复制**（非 wrapper）；
- 回退：无 tar.gz → None + stderr 警告；归档里找不到解释器 → None + 警告；
- 陈旧 shim（已存在的普通文件/错误指向）被替换成正确 wrapper。
"""

from __future__ import annotations

import io
import os
import subprocess
import tarfile
from collections.abc import Collection
from pathlib import Path

from lambchat_sandbox import pbs
from lambchat_sandbox import platform as plat

_FAKE_PY = '#!/bin/sh\necho "argv0=$0"\n'


def _make_tarball(path: Path, entries: dict[str, str], executable: Collection[str] = ()) -> None:
    """现场构造小 tar.gz：entries 为 {成员路径: 内容}，executable 成员给 0755。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(path, "w:gz") as tf:
        for name, content in entries.items():
            data = content.encode("utf-8")
            info = tarfile.TarInfo(name)
            info.size = len(data)
            info.mode = 0o755 if name in executable else 0o644
            tf.addfile(info, io.BytesIO(data))


def _setup(tmp_path: Path, entries: dict[str, str], executable: Collection[str] = ()):
    """resources + install_root 布局：resources 在 tmp_path/resources/python，
    install_root 在 tmp_path/python（shim 目录推得 tmp_path/bin，全在 tmp 内）。"""
    resources = tmp_path / "resources" / "python"
    install_root = tmp_path / "python"
    _make_tarball(resources / "python.tar.gz", entries, executable)
    return resources, install_root


# ---------------------------------------------------------------------------
# 解压 + shim
# ---------------------------------------------------------------------------


def test_ensure_runtime_extracts_flat_tarball_and_creates_executable_shim(tmp_path):
    resources, install_root = _setup(tmp_path, {"bin/python3": _FAKE_PY}, {"bin/python3"})
    bin_dir = pbs.ensure_runtime(resources, install_root)

    assert bin_dir == tmp_path / "bin"
    install_dir = install_root / pbs.PBS_TAG
    # 归档内容解压就位 + 幂等标记
    assert (install_dir / "bin" / "python3").exists()
    assert (install_dir / pbs.EXTRACT_MARKER).exists()
    # shim 存在且可执行
    shim = bin_dir / "python3"
    assert shim.exists()
    assert os.access(shim, os.X_OK)


def test_ensure_runtime_exec_wrapper_shim_points_at_real_interpreter(tmp_path):
    """POSIX shim 是 exec wrapper：假解释器的 $0（=真实 PBS 的 sys.executable
    语义）是归档里的解释器路径，而非 shim 自身。"""
    resources, install_root = _setup(
        tmp_path, {"python/bin/python3": _FAKE_PY}, {"python/bin/python3"}
    )
    bin_dir = pbs.ensure_runtime(resources, install_root)

    real_interp = (install_root / pbs.PBS_TAG / "python" / "bin" / "python3").resolve()
    proc = subprocess.run([str(bin_dir / "python3")], capture_output=True, text=True, timeout=10)
    assert proc.stdout.strip() == f"argv0={real_interp}"


def test_ensure_runtime_accepts_flat_layout_without_python_subdir(tmp_path):
    resources, install_root = _setup(tmp_path, {"bin/python3": _FAKE_PY}, {"bin/python3"})
    bin_dir = pbs.ensure_runtime(resources, install_root)
    proc = subprocess.run([str(bin_dir / "python3")], capture_output=True, text=True, timeout=10)
    assert proc.stdout.startswith("argv0=")
    assert str(bin_dir) not in proc.stdout  # $0 不是 shim 自身


# ---------------------------------------------------------------------------
# 幂等
# ---------------------------------------------------------------------------


def test_ensure_runtime_is_idempotent_and_skips_extraction_after_marker(tmp_path):
    resources, install_root = _setup(tmp_path, {"bin/python3": _FAKE_PY}, {"bin/python3"})
    first = pbs.ensure_runtime(resources, install_root)

    # 删掉 tar.gz：标记文件在，不重解压仍能返回 bin 目录（首启后的常态路径）
    (resources / "python.tar.gz").unlink()
    second = pbs.ensure_runtime(resources, install_root)
    assert second == first
    assert (first / "python3").exists()

    # 重复调用不炸
    assert pbs.ensure_runtime(resources, install_root) == first


def test_ensure_runtime_replaces_stale_shim(tmp_path):
    """已存在的陈旧 shim（错误指向的普通文件）被替换为正确 wrapper。"""
    resources, install_root = _setup(tmp_path, {"bin/python3": _FAKE_PY}, {"bin/python3"})
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(parents=True)
    stale = bin_dir / "python3"
    stale.write_text("#!/bin/sh\nexit 42\n", encoding="utf-8")
    os.chmod(stale, 0o755)

    pbs.ensure_runtime(resources, install_root)
    proc = subprocess.run([str(stale)], capture_output=True, text=True, timeout=10)
    assert proc.stdout.startswith("argv0=")
    assert proc.returncode == 0


# ---------------------------------------------------------------------------
# Windows 分支：shim 是 python3.exe 复制（Linux 宿主注入 win32 可全测）
# ---------------------------------------------------------------------------


def test_ensure_runtime_windows_shim_is_exe_copy(tmp_path, monkeypatch):
    monkeypatch.setattr(plat, "_sys_platform", "win32")
    resources, install_root = _setup(
        tmp_path, {"python/bin/python.exe": "MZ fake exe"}, {"python/bin/python.exe"}
    )
    bin_dir = pbs.ensure_runtime(resources, install_root)

    shim = bin_dir / "python3.exe"
    assert shim.exists()
    # 复制语义：内容与解释器一致（非 wrapper 文本）
    assert shim.read_text(encoding="utf-8") == "MZ fake exe"


def test_ensure_runtime_windows_install_only_layout(tmp_path, monkeypatch):
    """PBS Windows install_only 真实布局：解释器在 ``python/python.exe``
    （顶层 python 目录直接放 exe，无 bin 子目录）——同样认（M4 T4 审查）。"""
    monkeypatch.setattr(plat, "_sys_platform", "win32")
    resources, install_root = _setup(
        tmp_path, {"python/python.exe": "MZ root exe"}, {"python/python.exe"}
    )
    bin_dir = pbs.ensure_runtime(resources, install_root)

    assert bin_dir == tmp_path / "bin"
    shim = bin_dir / "python3.exe"
    assert shim.exists()
    assert shim.read_text(encoding="utf-8") == "MZ root exe"


def test_find_interpreter_prefers_python_bin_over_root_level(tmp_path, monkeypatch):
    """查找优先级：``python/bin`` > ``python``（Windows 根布局）> ``bin``（扁平），
    归档同时含多种布局时命中优先级最高的解释器。"""
    monkeypatch.setattr(plat, "_sys_platform", "win32")
    install_dir = tmp_path / "install"
    for base in ("python/bin", "python", "bin"):
        d = install_dir / base
        d.mkdir(parents=True, exist_ok=True)
        (d / "python.exe").write_text(f"MZ {base}", encoding="utf-8")

    found = pbs._find_interpreter(install_dir)
    assert found == install_dir / "python" / "bin" / "python.exe"


def test_find_interpreter_accepts_windows_root_layout_without_bin(tmp_path, monkeypatch):
    """只有 ``python/python.exe``（无任何 bin 目录）的归档也能定位解释器。"""
    monkeypatch.setattr(plat, "_sys_platform", "win32")
    install_dir = tmp_path / "install"
    d = install_dir / "python"
    d.mkdir(parents=True)
    (d / "python.exe").write_text("MZ only-root", encoding="utf-8")

    assert pbs._find_interpreter(install_dir) == d / "python.exe"


# ---------------------------------------------------------------------------
# 回退：无归档 / 归档缺解释器
# ---------------------------------------------------------------------------


def test_ensure_runtime_without_tarball_returns_none_with_warning(tmp_path, capsys):
    resources = tmp_path / "resources" / "python"
    install_root = tmp_path / "python"
    assert pbs.ensure_runtime(resources, install_root) is None
    err = capsys.readouterr().err
    assert "python.tar.gz" in err or "回退" in err


def test_ensure_runtime_tarball_without_interpreter_returns_none(tmp_path, capsys):
    resources, install_root = _setup(tmp_path, {"README.md": "no interpreter here"})
    assert pbs.ensure_runtime(resources, install_root) is None
    assert "python3" in capsys.readouterr().err or "python.exe" in capsys.readouterr().err


def test_default_paths_under_lambchat_home():
    """默认 resources / install_root / shim 目录的 ~/.lambchat 约定锁死。"""
    assert pbs.DEFAULT_RESOURCES_DIR == Path.home() / ".lambchat" / "resources" / "python"
    assert pbs.DEFAULT_INSTALL_ROOT == Path.home() / ".lambchat" / "python"
    # shim 目录由 install_root 推导：~/.lambchat/python → ~/.lambchat/bin
    assert pbs.shim_bin_dir(pbs.DEFAULT_INSTALL_ROOT) == Path.home() / ".lambchat" / "bin"


def test_extract_marker_name_is_dotted():
    """幂等标记是隐藏文件（不污染解释器目录枚举）。"""
    assert pbs.EXTRACT_MARKER.startswith(".")
