"""platform 抽象层：平台判定 + posix/windows 两套 shell 引用规则。

Windows 期望值全部来自微软 cmdline 解析文档（"Parsing C++ command-line
arguments"，learn.microsoft.com/cpp/c-language/parsing-c-command-line-arguments）
的引号/反斜杠交互条款：双引号包裹为单参数；紧邻引号的 N 个反斜杠，偶数个
→ 一半字面量且引号作定界，奇数个 → 一半（向下取整）字面量且引号本身为
字面量。测试内实现一个按该规则解析的裁判函数做往返校验，锁死转义不被
退化成朴素 ``replace('"', '\\"')``。
"""

from __future__ import annotations

import shlex
import sys

from lambchat_sandbox import platform as plat


def _parse_win_argv(line: str) -> list[str]:
    """按 MSVCRT 规则解析命令行为 argv（测试专用的往返裁判）。

    只需覆盖本模块 ``join_cmd`` 的产出形态：参数以单空格分隔、各参数被
    双引号完整包裹（引号内可含转义）。
    """
    argv: list[str] = []
    cur: list[str] = []
    quoted = False
    seen = False  # 当前参数是否已开张（支持空参数 ""）
    bs = 0
    for ch in line:
        if ch == "\\":
            bs += 1
            continue
        if ch == '"':
            cur.append("\\" * (bs // 2))
            if bs % 2:
                cur.append('"')  # 奇数个反斜杠：引号是字面量
            else:
                quoted = not quoted  # 偶数个：引号是定界符
                seen = True
            bs = 0
            continue
        cur.append("\\" * bs)
        bs = 0
        if ch in " \t" and not quoted:
            argv.append("".join(cur))
            cur = []
            seen = False
            continue
        cur.append(ch)
        seen = True
    cur.append("\\" * bs)
    if seen or cur:
        argv.append("".join(cur))
    return argv


# ---------- 平台判定 ----------


def test_platform_detection_defaults_to_host() -> None:
    assert plat._sys_platform == sys.platform
    assert plat.is_windows() == (sys.platform == "win32")
    assert plat.is_macos() == (sys.platform == "darwin")
    assert plat.is_posix() == (sys.platform != "win32")


def test_is_windows_true_only_on_win32(monkeypatch) -> None:
    monkeypatch.setattr(plat, "_sys_platform", "win32")
    assert plat.is_windows() is True
    assert plat.is_macos() is False
    assert plat.is_posix() is False


def test_is_macos_true_on_darwin_and_stays_posix(monkeypatch) -> None:
    monkeypatch.setattr(plat, "_sys_platform", "darwin")
    assert plat.is_windows() is False
    assert plat.is_macos() is True
    assert plat.is_posix() is True


def test_is_posix_true_on_linux(monkeypatch) -> None:
    monkeypatch.setattr(plat, "_sys_platform", "linux")
    assert plat.is_posix() is True
    assert plat.is_windows() is False
    assert plat.is_macos() is False


# ---------- daemon_platform：上报用平台归一（M4 T3） ----------


def test_daemon_platform_normalizes_to_three_values(monkeypatch) -> None:
    """sys.platform 归一为 linux/darwin/win32 三值（服务端只对 win32 分支）。"""
    monkeypatch.setattr(plat, "_sys_platform", "win32")
    assert plat.daemon_platform() == "win32"
    monkeypatch.setattr(plat, "_sys_platform", "darwin")
    assert plat.daemon_platform() == "darwin"
    monkeypatch.setattr(plat, "_sys_platform", "linux")
    assert plat.daemon_platform() == "linux"


def test_daemon_platform_unknown_falls_back_to_linux(monkeypatch) -> None:
    """未知平台保守归 linux：服务端按 posix（现状）处理，绝不错入 win32 分支。"""
    monkeypatch.setattr(plat, "_sys_platform", "freebsd14")
    assert plat.daemon_platform() == "linux"


# ---------- posix 引用 ----------


def test_shell_quote_posix_follows_shlex() -> None:
    for s in ["abc", "a b", 'he said "hi"', "trailing\\", 'a\\"b\\\\', "$HOME", "a;b", ""]:
        assert plat.shell_quote(s, platform="posix") == shlex.quote(s)


def test_shell_quote_posix_aliases_map_to_same_rules() -> None:
    # darwin/linux 等非 windows 平台串归一为 posix 规则（daemon 上报侧会传平台名）
    assert plat.shell_quote("a b", platform="darwin") == shlex.quote("a b")
    assert plat.shell_quote("a b", platform="linux") == shlex.quote("a b")


def test_shell_quote_none_uses_current_platform(monkeypatch) -> None:
    monkeypatch.setattr(plat, "_sys_platform", "linux")
    assert plat.shell_quote("a b") == shlex.quote("a b")
    monkeypatch.setattr(plat, "_sys_platform", "win32")
    assert plat.shell_quote("a b") == '"a b"'


# ---------- windows 引用：四个经典串 ----------


def test_windows_quote_classic_space() -> None:
    assert plat.shell_quote("a b", platform="windows") == '"a b"'


def test_windows_quote_classic_embedded_quotes() -> None:
    assert plat.shell_quote('he said "hi"', platform="windows") == '"he said \\"hi\\""'


def test_windows_quote_classic_trailing_backslash() -> None:
    assert plat.shell_quote("trailing\\", platform="windows") == '"trailing\\\\"'


def test_windows_quote_classic_backslash_quote_mix() -> None:
    # 规则 5/6 的交互用例：引号前的字面反斜杠要加倍再补转义，尾部反斜杠加倍
    assert plat.shell_quote('a\\"b\\\\', platform="windows") == '"a\\\\\\"b\\\\\\\\"'


def test_windows_quote_win32_alias() -> None:
    assert plat.shell_quote("a b", platform="win32") == '"a b"'


def test_windows_quote_always_wraps_plain_and_empty() -> None:
    assert plat.shell_quote("abc", platform="windows") == '"abc"'
    assert plat.shell_quote("", platform="windows") == '""'


def test_windows_quote_keeps_lone_backslash_literal() -> None:
    # 规则 4：不紧邻引号的反斜杠是字面量
    assert plat.shell_quote("a\\b", platform="windows") == '"a\\b"'
    assert plat.shell_quote("C:\\Program Files\\LambChat", platform="windows") == (
        '"C:\\Program Files\\LambChat"'
    )


_WIN_TORTURE = [
    "a b",
    'he said "hi"',
    "trailing\\",
    'a\\"b\\\\',
    "",
    "plain",
    "a\\b",
    "\\",
    "\\\\",
    '"',
    '""',
    '\\"',
    "space at end ",
    "\ttab",
    'mix \\" tail\\\\',
    "C:\\Program Files\\LambChat\\daemon.exe",
]


def test_windows_quote_roundtrips_through_msvcrt_parser() -> None:
    for s in _WIN_TORTURE:
        quoted = plat.shell_quote(s, platform="windows")
        assert _parse_win_argv(quoted) == [s], f"{s!r} -> {quoted!r} 未往返"


# ---------- join_cmd ----------


def test_join_cmd_posix_quotes_each_part() -> None:
    assert plat.join_cmd(["echo", "a b"], platform="posix") == "echo 'a b'"


def test_join_cmd_windows_quotes_each_part() -> None:
    assert plat.join_cmd(["a b", "c"], platform="windows") == '"a b" "c"'


def test_join_cmd_empty_list_is_empty_string() -> None:
    assert plat.join_cmd([], platform="posix") == ""
    assert plat.join_cmd([], platform="windows") == ""


def test_join_cmd_none_uses_current_platform(monkeypatch) -> None:
    monkeypatch.setattr(plat, "_sys_platform", "win32")
    # windows 规则外层始终包裹：普通参数同样带引号（往返安全优先）
    assert plat.join_cmd(["echo", "a b"]) == '"echo" "a b"'


def test_join_cmd_posix_roundtrips_through_shlex() -> None:
    parts = ["echo", "a b", "it's", "$HOME", "trailing\\"]
    assert shlex.split(plat.join_cmd(parts, platform="posix")) == parts


def test_join_cmd_windows_roundtrips_through_msvcrt_parser() -> None:
    parts = ["C:\\Program Files\\LambChat\\daemon.exe", "--msg", 'he said "hi"', "tail\\"]
    assert _parse_win_argv(plat.join_cmd(parts, platform="windows")) == parts
