"""
异常定义

定义系统中使用的所有自定义异常。
"""


class AgentError(Exception):
    """Agent 相关错误基类"""

    pass


class ConfigurationError(Exception):
    """配置错误"""

    pass


class ValidationError(Exception):
    """验证错误"""

    pass


class NotFoundError(Exception):
    """资源未找到错误"""

    pass


class AuthenticationError(Exception):
    """认证错误"""

    pass


class AuthorizationError(Exception):
    """授权错误"""

    pass


class StorageError(Exception):
    """存储错误"""

    pass


class LLMError(Exception):
    """LLM 调用错误"""

    pass


class ToolError(Exception):
    """工具执行错误"""

    pass


class SkillError(Exception):
    """技能相关错误"""

    pass


class SessionError(Exception):
    """会话相关错误"""

    pass
