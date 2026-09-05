"""确认策略：needs_confirm 三策略矩阵 + terminal_confirm 终端 y/N 交互。

- MUTATING_PATTERN 逐字锁定 Interfaces 正则（变更类命令清单 + 重定向/管道）；
- ``commands`` 策略保守误报取向：首词或 ``;``/``&``/``|``/空白后的变更类命令、
  ``>``/``>>``/``|`` 重定向都命中（``git status`` 只读也命中、管道也命中）；
- ``all`` 一律确认、``none`` 一律不确认、未知策略抛 ValueError；
- terminal_confirm 注入 input_fn：y/Y/yes 放行，其余（含空输入）拒绝。
"""

from __future__ import annotations

from collections.abc import Callable

import pytest

from lambchat_sandbox.confirm import MUTATING_PATTERN, needs_confirm, terminal_confirm

_SPEC_PATTERN = (
    r"(^|[;&|\s])(rm|mv|dd|chmod|chown|curl|wget|pip|npm|git|sudo|mkfs|shutdown|reboot)\b"
    r"|[>|]{1,2}\s*\S"
)

# (command, 是否命中 MUTATING_PATTERN)——commands 策略的期望矩阵
_COMMANDS_CASES = [
    ("echo hi", False),  # 纯只读：无变更词、无重定向
    ("ls -la /tmp", False),
    ("cat a", False),  # cat 本身不在变更清单，无重定向不命中
    ("pwd", False),
    ("rm -rf /tmp/x", True),  # 首词变更命令
    ("cat a > b", True),  # 输出重定向
    ("git status", True),  # git 在清单内（只读也保守命中）
    ("pip install requests", True),
    ("npm run build", True),
    ("sudo reboot", True),  # sudo 本身命中（reboot 兜底）
    ("echo done >> log.txt", True),  # 追加重定向
    ("echo hi | grep x", True),  # 管道（| 在重定向分支内）
    ("echo hi; rm x", True),  # 分号后的变更命令
    ("true && mv a b", True),  # && 链中的变更命令
]


def test_mutating_pattern_matches_spec_verbatim():
    # Interfaces 规定的正则逐字实现（隐式拼接后与规范串一致）
    assert MUTATING_PATTERN.pattern == _SPEC_PATTERN


@pytest.mark.parametrize("command,expected", _COMMANDS_CASES)
def test_needs_confirm_commands_policy_follows_mutating_pattern(command, expected):
    assert needs_confirm(command, "commands") is expected


@pytest.mark.parametrize("command,expected", _COMMANDS_CASES)
def test_needs_confirm_all_policy_confirms_everything(command, expected):
    # all 与命令内容无关，一律确认（expected 参数仅复用命令清单）
    assert needs_confirm(command, "all") is True


@pytest.mark.parametrize("command,expected", _COMMANDS_CASES)
def test_needs_confirm_none_policy_confirms_nothing(command, expected):
    # none 与命令内容无关，一律放行（rm -rf 也不确认——无人值守策略的含义）
    assert needs_confirm(command, "none") is False


def test_needs_confirm_unknown_policy_raises_value_error():
    with pytest.raises(ValueError, match="yolo"):
        needs_confirm("echo hi", "yolo")


# ---------------------------------------------------------------------------
# terminal_confirm：注入 input_fn 的纯交互判定
# ---------------------------------------------------------------------------


def _answering(answer: str) -> Callable[[str], str]:
    def fake_input(prompt: str) -> str:
        return answer

    return fake_input


@pytest.mark.parametrize("answer", ["y", "Y", "yes", "YES", "  y  "])
def test_terminal_confirm_accepts_yes_variants(answer):
    assert terminal_confirm("rm -rf /tmp/x", input_fn=_answering(answer)) is True


@pytest.mark.parametrize("answer", ["n", "N", "x", "", "no", "yes please"])
def test_terminal_confirm_rejects_everything_else(answer):
    # 直接回车（空串）默认拒绝：y/N 的 N 是默认项
    assert terminal_confirm("rm -rf /tmp/x", input_fn=_answering(answer)) is False


def test_terminal_confirm_prompt_shows_command_being_approved():
    prompts: list[str] = []

    def fake_input(prompt: str) -> str:
        prompts.append(prompt)
        return "n"

    assert terminal_confirm("cat a > b", input_fn=fake_input) is False
    assert "cat a > b" in prompts[0]
