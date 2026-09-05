"""内嵌 python-build-standalone（PBS）运行时装配。

daemon 执行环境不依赖用户系统的 python3：壳把 PBS ``install_only`` 归档随包
分发（Tauri resources），daemon 首启时解压就绪并建 shim 目录：

- **归档来源约定**：``<resources_dir>/python.tar.gz``（默认
  ``~/.lambchat/resources/python/python.tar.gz``）。daemon 不感知壳 resources
  路径——由 Tauri 侧安装/升级时把 ``resources/python/<platform>/python.tar.gz``
  拷贝到上述约定位置；
- **解压落位**：``<install_root>/<PBS_TAG>/``（默认 ``~/.lambchat/python/<tag>/``），
  归档保持 PBS install_only 原生布局（顶层 ``python/`` 目录；扁平 ``bin/`` 布局
  也认，供测试与自定义归档）；
- **幂等**：解压成功后写 ``EXTRACT_MARKER`` 标记文件，后续启动只补 shim、
  不重解压（tar.gz 首启后即可删除）；
- **shim**（``<install_root>/../bin/python3``，默认 ``~/.lambchat/bin/python3``）：
  - POSIX：exec wrapper 脚本——``exec <真实解释器> "$@"`` 使 argv[0] 指向归档
    内解释器，``python3 -c "import sys;print(sys.executable)"`` 因此命中
    ``~/.lambchat/python/<tag>/``（符号链接做不到：``sys.executable`` 会停在
    链接自身路径）；
  - Windows：复制语义（``python.exe`` → ``python3.exe``；wrapper/符号链接在
    win 无益）。Linux 全测，win 分支按此语义实现、真机验证见 M4 任务报告；
- **回退**：无归档 / 归档缺解释器 / 装配异常 → 打印警告返回 ``None``，调用方
  （daemon）回退系统 PATH，绝不阻断启动。

PBS tag / CPython 版本在本模块锁定（``PBS_TAG`` / ``PBS_PYTHON_VERSION``），
``client/scripts/fetch-pbs.py`` 构建期同源引用，升版本两处一起动。
"""

from __future__ import annotations

import os
import shlex
import shutil
import sys
import tarfile
from pathlib import Path

from lambchat_sandbox import platform as plat

#: 锁定的 python-build-standalone release tag（fetch-pbs.py 同源引用）。
PBS_TAG = "20260901"

#: 归档内的 CPython 版本（与 tag 组合成 release 资产名 cpython-<ver>+<tag>-…）。
PBS_PYTHON_VERSION = "3.12.14"

#: 归档文件名约定（壳 resources 分发后的名字）。
TARBALL_NAME = "python.tar.gz"

#: 幂等标记：install_dir 下存在即视为解压完成，不再重解压。
EXTRACT_MARKER = ".lambchat-extracted"

#: 默认归档查找目录：~/.lambchat/resources/python/python.tar.gz。
DEFAULT_RESOURCES_DIR = Path.home() / ".lambchat" / "resources" / "python"

#: 默认解压根：~/.lambchat/python/<tag>/。
DEFAULT_INSTALL_ROOT = Path.home() / ".lambchat" / "python"


def shim_bin_dir(install_root: Path) -> Path:
    """shim 目录由 install_root 推导：``~/.lambchat/python`` → ``~/.lambchat/bin``。"""
    return Path(install_root).parent / "bin"


def _interpreter_names() -> tuple[str, ...]:
    """平台对应的解释器文件名（Windows PBS 布局是 python.exe）。"""
    return ("python.exe",) if plat.is_windows() else ("python3",)


def _find_interpreter(install_dir: Path) -> Path | None:
    """在解压目录里定位解释器：PBS 布局 ``python/bin/…``，扁平布局 ``bin/…``。"""
    for base in ("python/bin", "bin"):
        for name in _interpreter_names():
            cand = install_dir / base / name
            if cand.is_file():
                return cand
    return None


def _extract(tarball: Path, install_root: Path) -> Path | None:
    """解压到临时目录、校验含解释器后原子改名进 ``install_root/<tag>``。

    返回 install_dir；归档里找不到解释器返回 None（临时目录已清理）。
    ``filter="data"`` 拒绝绝对路径/越界成员（tarfile 安全过滤器）。
    """
    install_dir = install_root / PBS_TAG
    tmp_dir = install_root / f".tmp-{PBS_TAG}"
    install_root.mkdir(parents=True, exist_ok=True)
    if tmp_dir.exists():
        shutil.rmtree(tmp_dir)
    with tarfile.open(tarball, "r:gz") as tf:
        tf.extractall(tmp_dir, filter="data")
    if _find_interpreter(tmp_dir) is None:
        shutil.rmtree(tmp_dir)
        return None
    if install_dir.exists():
        shutil.rmtree(install_dir)  # 无标记残留（半解压/崩溃现场）：重装
    tmp_dir.rename(install_dir)
    (install_dir / EXTRACT_MARKER).write_text(PBS_TAG + "\n", encoding="utf-8")
    return install_dir


def _install_shim(interp: Path, bin_dir: Path) -> Path:
    """在 bin_dir 建 python3 shim，返回 shim 路径。

    - Windows：复制解释器为 ``python3.exe``；
    - POSIX：exec wrapper（``#!/bin/sh\\nexec <解释器> "$@"``），陈旧 shim
      （普通文件/错误指向）先清再写。
    """
    bin_dir.mkdir(parents=True, exist_ok=True)
    shim = bin_dir / ("python3.exe" if plat.is_windows() else "python3")
    if plat.is_windows():
        shutil.copyfile(interp, shim)
        os.chmod(shim, 0o755)
        return shim
    if shim.is_symlink() or shim.exists():
        shim.unlink()
    target = shlex.quote(str(interp.resolve()))
    shim.write_text(f'#!/bin/sh\nexec {target} "$@"\n', encoding="utf-8")
    os.chmod(shim, 0o755)
    return shim


def ensure_runtime(
    resources_dir: Path | None = None, install_root: Path | None = None
) -> Path | None:
    """确保内嵌 Python 运行时就绪，返回 shim 所在 bin 目录（前置进子进程 PATH）。

    回退场景（无归档 / 归档缺解释器 / 解压异常）打印警告并返回 ``None``，
    调用方回退系统 PATH——绝不抛异常阻断 daemon 启动。幂等：已解压（标记
    文件在）则只补 shim。
    """
    resources = Path(resources_dir) if resources_dir is not None else DEFAULT_RESOURCES_DIR
    root = Path(install_root) if install_root is not None else DEFAULT_INSTALL_ROOT
    install_dir = root / PBS_TAG

    if not (install_dir / EXTRACT_MARKER).exists():
        tarball = resources / TARBALL_NAME
        if not tarball.is_file():
            print(
                f"[sandbox] 未找到内嵌 Python 归档 {tarball}，回退系统 PATH",
                file=sys.stderr,
                flush=True,
            )
            return None
        try:
            got = _extract(tarball, root)
        except (OSError, tarfile.TarError, ValueError) as exc:
            print(
                f"[sandbox] 内嵌 Python 归档解压失败（{tarball}）：{exc}，回退系统 PATH",
                file=sys.stderr,
                flush=True,
            )
            return None
        if got is None:
            names = " / ".join(_interpreter_names())
            print(
                f"[sandbox] 归档 {tarball} 内未找到解释器（python/bin/{names}），回退系统 PATH",
                file=sys.stderr,
                flush=True,
            )
            return None

    interp = _find_interpreter(install_dir)
    if interp is None:  # 标记在但解释器缺失（被用户清理等）：视为损坏，回退
        print(
            f"[sandbox] 内嵌 Python 目录异常（{install_dir} 缺解释器），回退系统 PATH",
            file=sys.stderr,
            flush=True,
        )
        return None
    _install_shim(interp, shim_bin_dir(root))
    return shim_bin_dir(root)
