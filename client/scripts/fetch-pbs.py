#!/usr/bin/env python3
"""构建期脚本：下载锁定的 python-build-standalone（PBS）install_only 归档。

产物约定（与 daemon 侧 ``client/lambchat_sandbox/pbs.py``、``tauri.conf.json``
的 ``bundle.resources`` 对齐）::

    <out>/<platform-tag>/python.tar.gz
    （默认 out = frontend/src-tauri/resources/python）

壳安装后 Tauri 把对应平台归档分发到 ``~/.lambchat/resources/python/python.tar.gz``，
daemon 首启解压（见 ``lambchat_sandbox.pbs.ensure_runtime``）。

tag / CPython 版本默认与 ``lambchat_sandbox.pbs`` 常量同源（锁定具体 release
tag 保可复现，不追 latest）；升版本改 ``pbs.py`` 一处即可，本脚本跟随。

用法::

    # 本机平台（默认）
    uv run python client/scripts/fetch-pbs.py
    # CI / 交叉打包：指定平台或全平台
    uv run python client/scripts/fetch-pbs.py --platform linux-x86_64
    uv run python client/scripts/fetch-pbs.py --platform all
"""

from __future__ import annotations

import argparse
import platform
import shutil
import sys
import urllib.request
from pathlib import Path

# 以 `python client/scripts/fetch-pbs.py` 直跑时也能 import lambchat_sandbox
_REPO_CLIENT = Path(__file__).resolve().parents[1]
if str(_REPO_CLIENT) not in sys.path:
    sys.path.insert(0, str(_REPO_CLIENT))

from lambchat_sandbox.pbs import PBS_PYTHON_VERSION, PBS_TAG  # noqa: E402

#: PBS GitHub 仓库（release 资产下载源）。
REPO = "astral-sh/python-build-standalone"

#: 默认 tag / 版本与 pbs.py 锁定值同源（防两处漂移）。
DEFAULT_TAG = PBS_TAG
DEFAULT_PYTHON_VERSION = PBS_PYTHON_VERSION

#: 默认输出：Tauri resources 约定目录（tauri.conf.json bundle.resources 同路径）。
DEFAULT_OUT = (
    Path(__file__).resolve().parents[2] / "frontend" / "src-tauri" / "resources" / "python"
)

#: 平台标签 → PBS release triple（install_only 资产名的平台段）。
PLATFORM_TRIPLES = {
    "linux-x86_64": "x86_64-unknown-linux-gnu",
    "linux-aarch64": "aarch64-unknown-linux-gnu",
    "windows-x86_64": "x86_64-pc-windows-msvc",
    "macos-arm64": "aarch64-apple-darwin",
    "macos-x64": "x86_64-apple-darwin",
}


def build_url(
    platform_tag: str,
    *,
    tag: str = DEFAULT_TAG,
    python_version: str = DEFAULT_PYTHON_VERSION,
) -> str:
    """平台标签 → PBS install_only 归档下载 URL（纯字符串构造，不做网络请求）。"""
    if platform_tag not in PLATFORM_TRIPLES:
        raise ValueError(f"未知平台 {platform_tag!r}，可选: {sorted(PLATFORM_TRIPLES)}")
    asset = f"cpython-{python_version}+{tag}-{PLATFORM_TRIPLES[platform_tag]}-install_only.tar.gz"
    return f"https://github.com/{REPO}/releases/download/{tag}/{asset}"


def host_platform() -> str:
    """宿主平台标签（system + machine 归入五平台之一）。"""
    system = platform.system()
    machine = platform.machine().lower()
    arm = machine in ("aarch64", "arm64")
    if system == "Linux":
        return "linux-aarch64" if arm else "linux-x86_64"
    if system == "Windows":
        return "windows-x86_64"
    if system == "Darwin":
        return "macos-arm64" if arm else "macos-x64"
    raise SystemExit(f"无法识别宿主平台: {system} {machine}")


def output_path(out_dir: Path, platform_tag: str) -> Path:
    """产物落位：<out>/<platform-tag>/python.tar.gz。"""
    return Path(out_dir) / platform_tag / "python.tar.gz"


def download(url: str, dest: Path) -> None:
    """流式下载到 .part 再原子改名（不留半截产物）。"""
    dest.parent.mkdir(parents=True, exist_ok=True)
    part = dest.with_name(dest.name + ".part")
    print(f"==> 下载 {url}")
    with urllib.request.urlopen(url, timeout=120) as resp, part.open("wb") as fh:
        shutil.copyfileobj(resp, fh)
    part.replace(dest)
    print(f"    -> {dest} ({dest.stat().st_size / 1e6:.1f} MB)")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="fetch-pbs",
        description="下载 python-build-standalone install_only 归档到 Tauri resources",
    )
    parser.add_argument(
        "--platform",
        default="host",
        choices=[*PLATFORM_TRIPLES, "host", "all"],
        help="目标平台（host=宿主，all=全部五平台；CI 交叉打包用 all）",
    )
    parser.add_argument(
        "--tag", default=DEFAULT_TAG, help=f"PBS release tag（默认锁定 {DEFAULT_TAG}）"
    )
    parser.add_argument(
        "--python-version",
        default=DEFAULT_PYTHON_VERSION,
        help=f"CPython 版本（默认 {DEFAULT_PYTHON_VERSION}）",
    )
    parser.add_argument("--out", default=str(DEFAULT_OUT), help="输出目录（默认 Tauri resources）")
    parser.add_argument("--force", action="store_true", help="已存在也重新下载")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.platform == "all":
        targets = sorted(PLATFORM_TRIPLES)
    elif args.platform == "host":
        targets = [host_platform()]
    else:
        targets = [args.platform]

    for target in targets:
        url = build_url(target, tag=args.tag, python_version=args.python_version)
        dest = output_path(Path(args.out), target)
        if dest.is_file() and not args.force:
            print(f"==> 已存在，跳过（--force 重下）: {dest}")
            continue
        download(url, dest)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
