"""
Human Tool 模型定义

支持多字段表单的 ask_human 工具的输入模型。
"""

from enum import Enum
from typing import Any, List, Optional

from pydantic import BaseModel, Field


class FieldType(str, Enum):
    """表单字段类型枚举"""

    TEXT = "text"
    """单行文本输入"""

    TEXTAREA = "textarea"
    """多行文本输入"""

    NUMBER = "number"
    """数字输入"""

    CHECKBOX = "checkbox"
    """复选框（布尔值）"""

    SELECT = "select"
    """下拉单选"""

    MULTI_SELECT = "multi_select"
    """下拉多选"""

    def __str__(self) -> str:
        return self.value


class FormField(BaseModel):
    """表单字段定义"""

    name: str = Field(
        ...,
        description="字段名称，用于标识返回值中的字段",
    )
    label: str = Field(
        ...,
        description="字段标签，显示给用户看的名称",
    )
    type: FieldType = Field(
        default=FieldType.TEXT,
        description="字段类型：text、textarea、number、checkbox、select、multi_select",
    )
    placeholder: Optional[str] = Field(
        default=None,
        description="输入框占位符文本",
    )
    default: Optional[Any] = Field(
        default=None,
        description="字段默认值",
    )
    required: bool = Field(
        default=True,
        description="是否必填",
    )
    options: Optional[List[str]] = Field(
        default=None,
        description="选项列表（仅 select 和 multi_select 类型使用）",
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "name": "username",
                    "label": "用户名",
                    "type": "text",
                    "placeholder": "请输入用户名",
                    "required": True,
                },
                {
                    "name": "description",
                    "label": "描述",
                    "type": "textarea",
                    "placeholder": "请输入详细描述",
                    "required": False,
                },
                {
                    "name": "environment",
                    "label": "部署环境",
                    "type": "select",
                    "options": ["development", "staging", "production"],
                    "default": "development",
                    "required": True,
                },
            ]
        }
    }


class AskHumanInput(BaseModel):
    """ask_human 工具的输入参数（支持多字段表单）"""

    message: str = Field(
        ...,
        description="向用户展示的提示消息，说明需要用户提供什么信息",
    )
    fields: List[FormField] = Field(
        default_factory=list,
        description="表单字段列表，定义需要用户填写的各个字段",
    )
    timeout: int = Field(
        default=300,
        ge=10,
        le=3600,
        description="等待响应的超时时间（秒），范围 10-3600",
    )
    allow_other: bool = Field(
        default=True,
        description="是否额外提供一个「其他意见」文本输入框，让用户可以填写选项中没有的建议，返回值中会包含 _other 字段",
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "message": "请填写数据库连接信息",
                    "fields": [
                        {
                            "name": "host",
                            "label": "主机地址",
                            "type": "text",
                            "required": True,
                        },
                        {
                            "name": "port",
                            "label": "端口",
                            "type": "number",
                            "default": 5432,
                            "required": True,
                        },
                        {
                            "name": "password",
                            "label": "密码",
                            "type": "text",
                            "required": True,
                        },
                    ],
                    "timeout": 300,
                }
            ]
        }
    }
