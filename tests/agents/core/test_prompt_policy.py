"""Prompt policy 契约：归属纪律条目必须存在于所有主 agent 的共享 prompt。"""

from src.agents.core.prompt_policy import (
    SAFETY_POLICY,
    WORKFLOW_POLICY,
    sandbox_shell_platform_section,
)
from src.agents.core.subagent_prompts import MAIN_AGENT_PROMPT_SECTIONS


def test_safety_policy_requires_explicit_attribution_for_record_answers():
    """回答来自记忆/历史会话的归属类问题（谁是 X 的供应商）时，断言必须
    有检索记录的显式支持；否则说明记录显示了什么、什么未确认。"""
    assert "explicitly" in SAFETY_POLICY
    assert "unconfirmed" in SAFETY_POLICY
    assert "possibly stale" in SAFETY_POLICY
    assert "confirmed-current" in SAFETY_POLICY


def test_attribution_discipline_reaches_all_main_agents():
    # MAIN_AGENT_PROMPT_SECTIONS 被 fast/search/team 三个 agent 的 prompt 组装引用
    for phrase in ("explicitly", "unconfirmed", "possibly stale", "confirmed-current"):
        assert phrase in WORKFLOW_POLICY
        assert any(phrase in section for section in MAIN_AGENT_PROMPT_SECTIONS)


def test_shell_platform_section_empty_for_unknown_only():
    """空串/未知平台（云端沙箱、未上报、查询失败）不加平台段：prompt 逐字节保持
    现状，provider 前缀缓存零失效，也绝不错入 Windows 方言分支。"""
    assert sandbox_shell_platform_section("") == ""
    assert sandbox_shell_platform_section("winxp") == ""


def test_shell_platform_section_linux_injects_local_machine_identity():
    """linux 本地 daemon 也必须注入「沙箱=用户本机」身份段。

    生产会话 26ed193a 实测：linux daemon 不加段时，模型自认「隔离沙箱、
    跟用户电脑完全不连通」，当面否认控制能力并反指用户可能中了远控木马
    ——而命令实际就跑在用户机器上。身份认知正确优先于前缀缓存。"""
    section = sandbox_shell_platform_section("linux")
    assert "user's own real computer" in section
    assert "never claim" in section.lower()
    # 谨慎操作纪律：真实机器上删改要先确认、新文件优先会话 workspace
    assert "confirm" in section.lower()
    assert "session workspace" in section


def test_local_machine_identity_reaches_win32_and_darwin():
    """win32/darwin 的方言段之前只在开头顺带提一句「用户机器」，缺身份与
    谨慎纪律框架；身份段必须补上，且以纯尾部追加方式——方言段历史字节
    保持原样（存量会话已缓存前缀零失效），身份段接在最后。"""
    markers = {"win32": "cmd.exe", "darwin": "macOS"}
    for platform, marker in markers.items():
        section = sandbox_shell_platform_section(platform)
        assert "user's own real computer" in section
        # 方言段原字节在前的纯追加：分叉点不前移
        assert section.startswith("### Local Machine Shell:")
        assert section.index(marker) < section.index("user's own real computer")


def test_shell_platform_section_win32_guides_cmdexe_syntax():
    """win32 daemon：提示 cmd.exe 语法要点（%ERRORLEVEL%、%VAR%、无 POSIX 语法），
    否则模型默认生成 POSIX 命令在 cmd.exe 全军覆没（生产实测根因之一）。"""
    section = sandbox_shell_platform_section("win32")
    assert "cmd.exe" in section
    assert "%ERRORLEVEL%" in section
    assert "%LAMBCHAT_WORKSPACE%" in section
    # 反面约束：别把 POSIX 习惯带进 cmd.exe
    assert "$?" not in section.replace("$LAMBCHAT", "")


def test_shell_platform_section_darwin_guides_bsd_userland():
    """darwin daemon：macOS 是 POSIX shell 但 BSD userland（无 /proc、无 free），
    提示用 python3 做跨平台活。"""
    section = sandbox_shell_platform_section("darwin")
    assert "macOS" in section
    assert "python3" in section
