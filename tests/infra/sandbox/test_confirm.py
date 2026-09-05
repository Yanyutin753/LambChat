"""服务端确认策略：needs_confirm 三档判定（自 client/lambchat_sandbox/confirm.py 移植，语义互锁）。"""

import pytest

from src.infra.sandbox.confirm import POLICIES, needs_confirm


@pytest.mark.parametrize("policy", ["all", "commands"])
@pytest.mark.parametrize(
    "command",
    [
        "rm -rf /tmp/x",
        "echo hi; rm x",
        "true && mv a b",
        "cat a > b",
        "echo hi | grep x",
        "python3 -c 'pass' >> log",
    ],
)
def test_mutating_commands_confirm(policy, command):
    assert needs_confirm(command, policy) is True


def test_readonly_ls_passes_under_commands():
    assert needs_confirm("ls -la .", "commands") is False


def test_git_status_confirms_under_commands():
    # 保守误报取向：git 整体在清单内（M2 接受的取舍，移植保持一致）
    assert needs_confirm("git status", "commands") is True


def test_none_policy_passes_everything():
    assert needs_confirm("rm -rf /", "none") is False


def test_all_policy_confirms_everything():
    assert needs_confirm("ls", "all") is True


def test_unknown_policy_raises():
    with pytest.raises(ValueError, match="未知确认策略"):
        needs_confirm("ls", "yolo")


def test_policies_tuple():
    assert POLICIES == ("all", "commands", "none")
