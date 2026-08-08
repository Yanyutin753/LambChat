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

    RADIO = "radio"
    """平铺单选"""

    MULTI_SELECT = "multi_select"
    """下拉多选"""

    def __str__(self) -> str:
        return self.value


class FormField(BaseModel):
    """表单字段定义"""

    name: str = Field(
        default="choice",
        description="返回值中的字段名",
    )
    label: str = Field(
        default="请选择",
        description="用户可见标签",
    )
    type: FieldType = Field(
        default=FieldType.TEXT,
        description="输入类型",
    )
    placeholder: Optional[str] = Field(
        default=None,
        description="占位文本",
    )
    default: Optional[Any] = Field(
        default=None,
        description="默认值",
    )
    required: bool = Field(
        default=True,
        description="是否必填",
    )
    options: Optional[List[str]] = Field(
        default=None,
        description="select/radio/multi_select 的选项",
    )
    multiple: bool = Field(
        default=False,
        description="是否多选",
    )


class AskHumanInput(BaseModel):
    """ask_human 工具的输入参数（支持多字段表单）"""

    message: str = Field(
        ...,
        description="向用户展示的问题",
    )
    fields: List[FormField] = Field(
        default_factory=list,
        description="结构化表单字段",
    )
    choices: Optional[List[str]] = Field(
        default=None,
        description="简写选项；设置后自动生成 choice 字段",
    )
    multiple: bool = Field(
        default=False,
        description="choices 是否多选",
    )
    timeout: int = Field(
        default=300,
        ge=10,
        le=3600,
        description="等待秒数（10-3600）",
    )
    allow_other: bool = Field(
        default=True,
        description="添加其他意见输入，返回 _other",
    )
