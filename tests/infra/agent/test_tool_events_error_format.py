"""工具错误事件格式化：AppError 必须走 display_message 插值。

生产实测：本地沙箱命令失败上抛 AppError 后，模型与前端看到的都是
``Local sandbox execution failed: {{detail}}`` 原文——``str(AppError)`` 返回
未插值的默认模板，插值版在 ``AppError.display_message``。
"""

from src.infra.agent.events.tool_events import ToolEventMixin
from src.kernel.errors import AppError, ErrorCode


def _format(error) -> str:
    return ToolEventMixin()._format_tool_error("execute", error)


def test_app_error_interpolates_display_message():
    err = AppError(ErrorCode.SANDBOX_EXEC_FAILED, args={"detail": "illegal cwd"})
    text = _format(err)
    assert "{{detail}}" not in text
    assert "illegal cwd" in text


def test_app_error_falls_back_to_error_name_when_args_missing():
    """args 未提供占位值时保留 ``{{param}}`` 原文（display_message 语义），
    但仍不应把异常类名拼错——格式保持 [AppError] 前缀链路可解析。"""
    err = AppError(ErrorCode.SANDBOX_EXEC_FAILED)
    text = _format(err)
    assert "[AppError]" in text
    assert "Local sandbox execution failed" in text


def test_plain_exception_format_unchanged():
    text = _format(RuntimeError("boom"))
    assert text == "[MCP Tool Error] execute failed: [RuntimeError] boom"
