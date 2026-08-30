"""
异常定义

系统自定义异常统一继承 :class:`src.kernel.errors.AppError`，携带错误码与
默认 HTTP 状态码，可不经路由层手工转换直接冒泡到全局异常处理器。

兼容两种构造方式::

    raise NotFoundError("some message")            # 默认码 not_found / 404
    raise NotFoundError(ErrorCode.MESSAGE_NOT_FOUND)  # 精确错误码
"""

from typing import Union

from src.kernel.errors import AppError, ErrorCode

CodeOrMessage = Union[ErrorCode, str, None]


class _RetrofittedError(AppError):
    """旧异常类的公共改造模板：位置参数可以是 ErrorCode 或消息字符串。"""

    _default_code: ErrorCode

    def __init__(self, code_or_message: CodeOrMessage = None):
        if isinstance(code_or_message, ErrorCode):
            super().__init__(code_or_message)
        else:
            super().__init__(
                self._default_code, message=code_or_message or self._default_code.default_message
            )


class AgentError(_RetrofittedError):
    """Agent 相关错误基类"""

    _default_code = ErrorCode.AGENT_ERROR


class ConfigurationError(_RetrofittedError):
    """配置错误"""

    _default_code = ErrorCode.CONFIGURATION_ERROR


class ValidationError(_RetrofittedError):
    """验证错误"""

    _default_code = ErrorCode.VALIDATION_ERROR


class NotFoundError(_RetrofittedError):
    """资源未找到错误"""

    _default_code = ErrorCode.NOT_FOUND


class AuthenticationError(_RetrofittedError):
    """认证错误"""

    _default_code = ErrorCode.UNAUTHORIZED


class AuthorizationError(_RetrofittedError):
    """授权错误"""

    _default_code = ErrorCode.FORBIDDEN


class StorageError(_RetrofittedError):
    """存储错误"""

    _default_code = ErrorCode.STORAGE_ERROR


class LLMError(_RetrofittedError):
    """LLM 调用错误"""

    _default_code = ErrorCode.LLM_ERROR


class ToolError(_RetrofittedError):
    """工具执行错误"""

    _default_code = ErrorCode.TOOL_ERROR


class SkillError(_RetrofittedError):
    """技能相关错误"""

    _default_code = ErrorCode.SKILL_ERROR


class SessionError(_RetrofittedError):
    """会话相关错误"""

    _default_code = ErrorCode.SESSION_ERROR


class EmailNotVerifiedError(AppError):
    """邮箱未验证错误"""

    def __init__(self, message: str, email: str):
        super().__init__(ErrorCode.EMAIL_NOT_VERIFIED, message=message)
        self.email = email


class AccountNotActiveError(AppError):
    """账户未激活错误"""

    def __init__(self, message: str, email: str):
        super().__init__(ErrorCode.ACCOUNT_NOT_ACTIVE, message=message)
        self.email = email
