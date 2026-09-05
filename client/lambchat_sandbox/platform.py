"""平台抽象层：平台判定与跨平台 shell 引用。

M4 三平台支持的地基模块。平台判定统一读模块级 ``_sys_platform``（默认取
``sys.platform``），测试可用 monkeypatch 注入伪造平台（``"win32"`` /
``"darwin"`` / ``"linux"``），无需真的跨平台跑。

Windows cmd.exe 引用规则出处（微软 cmdline 解析文档 "Parsing C++
command-line arguments"，
learn.microsoft.com/en-us/cpp/c-language/parsing-c-command-line-arguments）：

- 规则 2：双引号包裹的字符串被解析为单个参数，其中的空白不断词；
- 规则 4：反斜杠仅当紧邻双引号时才有转义含义，其余场合按字面量；
- 规则 5/6（引号/反斜杠交互）：引号前有 N 个反斜杠——N 为偶数时 N/2 个
  是字面量、该引号作字符串定界符；N 为奇数时 (N-1)/2 个是字面量、且该
  引号本身是字面引号。

据此把任意参数编码为安全命令行片段：外层始终双引号包裹；参数内每个字面
``"`` 前置 ``2N+1`` 个反斜杠（N 为其前紧邻的字面反斜杠数——先加倍原有
反斜杠，再补一个转义引号的反斜杠）；收尾引号前若有 N 个字面反斜杠，加倍
为 2N（否则按规则 5 会被吃掉一半并提前闭合引号）。
"""

from __future__ import annotations

import shlex
import sys

# 模块级平台串：默认跟随真实宿主；测试可 monkeypatch 注入伪造值。
_sys_platform: str = sys.platform

# 视为 windows 规则的平台参数别名（shell_quote 的显式 platform 入参用）。
_WINDOWS_PLATFORM_ALIASES = frozenset({"windows", "win32"})


def is_windows() -> bool:
    """当前是否 Windows（``sys.platform == "win32"``，64 位 Windows 同值）。"""
    return _sys_platform == "win32"


def is_macos() -> bool:
    """当前是否 macOS（``sys.platform == "darwin"``）。"""
    return _sys_platform == "darwin"


def is_posix() -> bool:
    """当前是否 POSIX 系（Linux/macOS；本项目三分类里即“非 Windows”）。"""
    return not is_windows()


def current_platform() -> str:
    """当前平台归一化串：``"windows"`` 或 ``"posix"``（供显式传参复用）。"""
    return "windows" if is_windows() else "posix"


def daemon_platform() -> str:
    """上报用平台串：``sys.platform`` 归一为 ``linux``/``darwin``/``win32``。

    服务端（文件命令生成平台分支）只对 ``win32`` 改用 cmd 引用与无 mkdir
    前缀，其余一律 posix（现状）；未知平台（如 freebsd）保守归 ``linux``，
    绝不错入 windows 分支。
    """
    if _sys_platform == "win32":
        return "win32"
    if _sys_platform == "darwin":
        return "darwin"
    return "linux"


def _quote_windows(s: str) -> str:
    """按微软 cmdline 规则给单个参数加引号（规则条款见模块 docstring）。"""
    out: list[str] = ['"']
    backslashes = 0
    for ch in s:
        if ch == "\\":
            backslashes += 1
            continue
        if ch == '"':
            # 字面引号前置 2N+1 个反斜杠（规则 5/6 的逆向编码）
            out.append("\\" * (backslashes * 2 + 1))
            out.append('"')
        else:
            # 不紧邻引号的反斜杠是字面量（规则 4），按原样透传
            out.append("\\" * backslashes)
            out.append(ch)
        backslashes = 0
    # 收尾引号前的 N 个字面反斜杠加倍为 2N，避免被解析成“转义掉闭合引号”
    out.append("\\" * (backslashes * 2))
    out.append('"')
    return "".join(out)


def shell_quote(s: str, platform: str | None = None) -> str:
    """按平台把单个参数编码为安全的命令行片段。

    - posix（含 darwin/linux 归一）：与 :func:`shlex.quote` 一致（单引号包裹）；
    - windows（别名 win32）：cmd.exe/MSVCRT 双引号规则，见模块 docstring；
    - ``platform=None``：按当前宿主平台（``_sys_platform``）。
    """
    plat = platform if platform is not None else current_platform()
    if plat in _WINDOWS_PLATFORM_ALIASES:
        return _quote_windows(s)
    return shlex.quote(s)


def join_cmd(parts: list[str], platform: str | None = None) -> str:
    """把参数列表拼成单条命令行串（逐参数引用、单空格连接）。

    ``platform=None`` 时按当前宿主平台解析一次，避免逐参数重复判定。
    """
    plat = platform if platform is not None else current_platform()
    return " ".join(shell_quote(part, platform=plat) for part in parts)
