"""CLI 自更新：查 GitHub latest release → 下载平台资产 → 原子替换自体。

版本闭环（M4 T6）的客户端半边：服务端最低版本拒连（T5）把过旧的 daemon
挡在门外，本模块提供升级出口。只服务 CLI/PyInstaller onefile 直跑形态；
Tauri 壳形态的更新归壳的 updater，不经过这里。

流程（:func:`perform_update`）：

1. :func:`check_latest`：GET ``releases/latest``（GITHUB_TOKEN 可选）→ 找
   ``lambchat-daemon-<host-triple>`` 资产 → 版本高于当前才继续；
2. 流式下载到 ``<argv[0]>.new``，边下边算 sha256（release 资产带 digest
   则校验，不带则跳过并在结果里注明）；
3. 替换自体：onefile 二进制在跑时不能直接覆盖自身——POSIX 用
   ``os.replace`` 原子换；Windows 分支先把旧件改名 ``.old`` 再换（运行中
   的 exe 可以改名、不能被覆盖删除；改名序为后验项，真机行为留 CI/人工）；
4. ``chmod +x``（保留原 mode 加执行位）→ 返回「已更新到 X，重启后生效」。

无新版本/无匹配资产/仓库无 release 都返回 None/提示语，网络与校验失败抛
:class:`SelfUpdateError`（CLI 转成友好错误行）。
"""

from __future__ import annotations

import hashlib
import os
import platform as stdlib_platform
import stat
import sys
from pathlib import Path

import httpx

import lambchat_sandbox
from lambchat_sandbox import platform as plat

DEFAULT_REPO = "Yanyutin753/LambChat"
ASSET_PREFIX = "lambchat-daemon-"
_API_BASE = "https://api.github.com/repos"
_TIMEOUT = httpx.Timeout(30.0, read=120.0)  # 查询 30s；资产下载单次 read 放宽


class SelfUpdateError(Exception):
    """更新失败（下载/校验/替换），message 面向 CLI 直出。"""


def _current_version(explicit: str | None) -> str:
    """当前版本：显式传入优先，否则取包 ``__version__``（调用时读取，可测）。"""
    return explicit if explicit is not None else lambchat_sandbox.__version__


def _parse_version(version: str) -> tuple[int, ...]:
    """版本串（容忍 ``v`` 前缀）→ int 元组；非数字段容错按 0。

    数字判定必须 ``isascii() and isdigit()``：Unicode 数字（如阿拉伯-印度数字
    "٥"）``isdigit()`` 为真且 ``int()`` 可转成 5——伪造 tag "٥.٠" 会被当成
    (5,0) 高于一切正常版本。非 ASCII 数字一律按非数字段容错 0。
    """
    v = version.strip()
    if v[:1] in ("v", "V"):
        v = v[1:]
    return (
        tuple(int(part) if part.isascii() and part.isdigit() else 0 for part in v.split("."))
        if v
        else (0,)
    )


def _ensure_packaged_target(target: Path) -> None:
    """自更新护栏：仅打包后的二进制可自替换（M4 T8）。

    ``python -m lambchat_sandbox update`` / 源码直跑时，argv[0] 是 .py 入口或
    解释器非 frozen（无 ``sys.frozen`` 标记）——把 release 资产 ``os.replace``
    到这种目标会砖化安装源（.py 被换成二进制、site-packages 树被换掉一半）。
    直接拒绝，提示改走原安装渠道。fail-fast：先于网络查询，不浪费请求。
    """
    if target.suffix == ".py" or not bool(getattr(sys, "frozen", False)):
        raise SelfUpdateError(
            f"仅支持打包后的二进制自更新（目标 {target} 不是打包产物）；"
            "python -m / 源码运行请通过原安装渠道升级"
        )


def host_triple(*, sys_platform: str | None = None, machine: str | None = None) -> str:
    """当前宿主的资产三元组（与 client/scripts/fetch-pbs.py 的映射同源）。

    linux 按 machine 分 ``x86_64/aarch64-unknown-linux-gnu``；darwin 暂定
    ``aarch64-apple-darwin``（M4 单 arm64，universal 列 M5）；win32 暂定
    ``x86_64-pc-windows-msvc``（暂无 arm64 Windows 构建）。参数供测试注入，
    缺省读真实宿主。
    """
    plat_name = sys_platform if sys_platform is not None else plat.daemon_platform()
    arch_raw = (machine if machine is not None else stdlib_platform.machine()).lower()
    if plat_name == "win32":
        return "x86_64-pc-windows-msvc"
    if plat_name == "darwin":
        return "aarch64-apple-darwin"
    arch = "aarch64" if arch_raw in ("aarch64", "arm64") else "x86_64"
    return f"{arch}-unknown-linux-gnu"


def _headers() -> dict[str, str]:
    headers = {"Accept": "application/vnd.github+json"}
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _fetch_latest(
    repo: str,
    *,
    current_version: str | None = None,
    transport: httpx.BaseTransport | None = None,
) -> tuple[str, str, str | None] | None:
    """查 latest release，返回 ``(新版本, 资产 URL, digest|None)``。

    无 release（404）/无匹配平台资产/版本不高于当前 → None。其余非 2xx
    视为网络/接口异常，抛 :class:`SelfUpdateError`。
    """
    current = _parse_version(_current_version(current_version))
    with httpx.Client(timeout=_TIMEOUT, transport=transport, follow_redirects=True) as client:
        resp = client.get(f"{_API_BASE}/{repo}/releases/latest", headers=_headers())
        if resp.status_code == 404:
            return None  # 仓库尚无 release：无更新可用
        if not resp.is_success:
            raise SelfUpdateError(f"查询 release 失败: HTTP {resp.status_code}")
        triple = host_triple()
        for asset in resp.json().get("assets", []):
            if asset.get("name", "").startswith(f"{ASSET_PREFIX}{triple}"):
                version = _parse_version(resp.json().get("tag_name", ""))
                if version > current:
                    return (
                        resp.json().get("tag_name", "").lstrip("vV"),
                        asset["browser_download_url"],
                        asset.get("digest"),
                    )
                return None  # 找到平台资产但已是最新
    return None  # 无匹配平台资产


def check_latest(
    repo: str = DEFAULT_REPO,
    *,
    current_version: str | None = None,
    transport: httpx.BaseTransport | None = None,
) -> tuple[str, str] | None:
    """有更新的平台资产则返回 ``(版本, 下载 URL)``，否则 None。

    ``transport`` 供测试注入 httpx.MockTransport。
    """
    found = _fetch_latest(repo, current_version=current_version, transport=transport)
    return (found[0], found[1]) if found else None


def _download_to(
    url: str, dest: Path, *, transport: httpx.BaseTransport | None = None
) -> tuple[bytes, str]:
    """流式下载到 dest（边下边算 sha256）；返回 ``(十六进制摘要, 算法)``。

    失败清理半成品 dest 并抛 SelfUpdateError。
    """
    hasher = hashlib.sha256()
    try:
        with httpx.Client(timeout=_TIMEOUT, transport=transport, follow_redirects=True) as client:
            with client.stream("GET", url) as resp:
                resp.raise_for_status()
                with dest.open("wb") as fh:
                    for chunk in resp.iter_bytes():
                        fh.write(chunk)
                        hasher.update(chunk)
    except httpx.HTTPError as exc:
        dest.unlink(missing_ok=True)
        raise SelfUpdateError(f"下载失败: {exc}") from exc
    return hasher.hexdigest(), "sha256"


def perform_update(
    repo: str = DEFAULT_REPO,
    *,
    target_path: Path | None = None,
    current_version: str | None = None,
    transport: httpx.BaseTransport | None = None,
) -> str:
    """执行自更新，返回面向用户的描述串（CLI 直出）。

    ``target_path`` 缺省取 ``Path(sys.argv[0]).resolve()``（替换自体），
    供测试注入假目标文件。护栏先行（:func:`_ensure_packaged_target`）：
    非打包形态（.py 目标 / 非 frozen 解释器）在查网络之前就被拒绝。
    """
    target = target_path if target_path is not None else Path(sys.argv[0]).resolve()
    _ensure_packaged_target(target)

    latest = _fetch_latest(repo, current_version=current_version, transport=transport)
    if latest is None:
        return f"已是最新（{_current_version(current_version)}），或最新 release 无当前平台资产，无需更新"
    version, url, digest = latest
    new_path = target.with_name(target.name + ".new")

    actual_hex, _ = _download_to(url, new_path, transport=transport)

    verify_note = "release 未提供 digest，跳过校验"
    if digest:
        expected = digest.split(":", 1)[1] if ":" in digest else digest
        if expected.lower() != actual_hex:
            new_path.unlink(missing_ok=True)
            raise SelfUpdateError("sha256 校验失败：资产内容与 release 摘要不符")
        verify_note = "sha256 校验通过"

    if plat.is_windows():
        # Windows：运行中的 exe 不能被覆盖但可以改名——旧件先挪 .old（残留的
        # 更早 .old 先清掉），新件再换到原名。改名序为后验项：真机 Windows
        # 行为留 CI（app-release 矩阵）与人工验证。
        old_path = target.with_name(target.name + ".old")
        old_path.unlink(missing_ok=True)
        os.replace(target, old_path)
        os.replace(new_path, target)
    else:
        os.replace(new_path, target)  # POSIX：同目录 rename 原子换
    target.chmod(target.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return f"已更新到 {version}，重启后生效（{verify_note}）"
