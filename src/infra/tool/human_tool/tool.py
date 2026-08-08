"""
Human Tool 实现

支持多字段表单的 ask_human 工具的 LangChain 工具实现。
"""

import json
from typing import Any, Dict, List, Optional, Type

from langchain_core.tools import BaseTool

from src.api.routes.human import create_approval, wait_for_response
from src.infra.async_utils import run_blocking_io
from src.infra.logging import get_logger
from src.infra.tool.human_tool.models import AskHumanInput, FieldType, FormField

logger = get_logger(__name__)


async def _json_dumps_result(data: dict[str, Any]) -> str:
    return await run_blocking_io(json.dumps, data, ensure_ascii=False)


class AskHumanTool(BaseTool):
    """
    请求人工输入的工具（支持多字段表单）

    当 Agent 遇到不确定的情况时，可以调用此工具请求人工输入。
    工具会阻塞直到用户响应或超时。

    支持多种字段类型：
    - text: 单行文本输入
    - textarea: 多行文本输入
    - number: 数字输入
    - checkbox: 复选框（布尔值）
    - select: 下拉单选
    - multi_select: 下拉多选

    使用场景：
    - 需要用户确认敏感操作
    - 需要用户提供额外信息（如表单）
    - 遇到多种可能的方案需要用户选择
    - 不确定用户意图时请求澄清
    """

    name: str = "ask_human"
    description: str = """向用户提问并等待回复。仅在缺少必要信息、需要用户选择，或需确认敏感/不可逆操作时使用。
简单选项用 choices（multiple 控制多选）；结构化表单用 fields。返回字段 JSON、超时或拒绝状态。"""
    args_schema: Type[AskHumanInput] = AskHumanInput
    return_direct: bool = False

    # 从 context 注入（可选，优先使用 TraceContext）
    session_id: str = ""

    def _run(
        self,
        message: str,
        fields: Optional[List[FormField]] = None,
        timeout: int = 300,
    ) -> str:
        """同步执行（不支持，返回错误）"""
        return "Error: ask_human only supports async execution. Use ainvoke instead."

    async def _arun(
        self,
        message: str,
        fields: Optional[List[FormField]] = None,
        choices: Optional[List[str]] = None,
        multiple: bool = False,
        timeout: int = 300,
        allow_other: bool = False,
    ) -> str:
        """
        异步执行：创建审批请求并等待响应

        Args:
            message: 向用户展示的提示消息
            fields: 表单字段列表
            timeout: 超时时间（秒），范围 10-3600

        Returns:
            JSON 字符串，包含状态和字段值或错误消息
        """
        # 设置默认值
        fields = self._expand_short_choices(fields, choices, multiple)

        # 解析字段并设置默认值
        parsed_fields = await run_blocking_io(self._parse_fields, fields)

        # 如果启用了 allow_other，追加一个独立的「其他意见」文本字段
        # 使用 _ 前缀命名空间，避免与用户字段冲突
        if allow_other:
            parsed_fields.append(
                FormField(
                    name="_other",
                    label="其他意见",
                    type=FieldType.TEXTAREA,
                    placeholder="除上述选项外，您还有其他想法或建议吗？",
                    required=False,
                )
            )

        # 获取当前请求上下文
        from src.infra.logging.context import TraceContext

        ctx = TraceContext.get_request_context()
        session_id = self.session_id or ctx.session_id
        run_id = ctx.run_id
        user_id = ctx.user_id

        # 构建审批类型和字段列表
        approval_type = "form"

        # 将字段序列化为 dict 列表
        field_dicts = [f.model_dump() for f in parsed_fields] if parsed_fields else []

        # 创建审批请求
        approval = await create_approval(
            message=message,
            approval_type=approval_type,
            fields=field_dicts,
            session_id=session_id or None,
            user_id=user_id,
        )

        # 通过 SSE 流发送 approval_required 事件
        await self._send_approval_event(
            approval, session_id, run_id, parsed_fields, timeout=timeout
        )

        # 等待用户响应
        response = await wait_for_response(approval.id, timeout=timeout)

        if response is None:
            # 超时：构建超时响应
            result = {
                "status": "timeout",
                "message": f"等待用户响应超时（{timeout}秒）",
                "values": self._get_default_values(parsed_fields),
            }
            return await _json_dumps_result(result)

        if not response.approved:
            # 用户拒绝
            result = {
                "status": "rejected",
                "message": "用户拒绝了此请求",
                "values": {},
            }
            return await _json_dumps_result(result)

        # 成功：解析用户响应
        # response.response 现在是 dict 类型
        if response.response and isinstance(response.response, dict):
            values = response.response
        else:
            values = self._get_default_values(parsed_fields)

        result = {
            "status": "success",
            "message": "用户已响应",
            "values": values,
        }
        return await _json_dumps_result(result)

    def _expand_short_choices(
        self,
        fields: Optional[List[FormField]],
        choices: Optional[List[str]],
        multiple: bool,
    ) -> list[Any]:
        if fields:
            return fields
        if not choices:
            return []
        return [
            {
                "name": "choice",
                "label": "请选择",
                "type": "multi_select" if multiple else "radio",
                "options": choices,
                "multiple": multiple,
                "required": True,
            }
        ]

    def _parse_fields(self, fields: Any) -> List[FormField]:
        """
        解析字段列表并设置默认值

        Args:
            fields: 字段列表（可能是 FormField 对象、字典或 JSON 字符串）

        Returns:
            解析后的 FormField 列表
        """
        # 处理 fields 是 JSON 字符串的情况（LLM 有时会这样传参）
        if isinstance(fields, str):
            try:
                fields = json.loads(fields)
            except json.JSONDecodeError:
                logger.warning(f"Failed to parse fields as JSON: {fields[:100]}...")
                fields = []

        # 确保 fields 是列表
        if not isinstance(fields, list):
            logger.warning(f"fields is not a list: {type(fields)}")
            fields = []

        parsed = []
        for field in fields:
            if isinstance(field, FormField):
                if field.options and field.type == FieldType.TEXT:
                    field = field.model_copy(
                        update={
                            "type": FieldType.MULTI_SELECT if field.multiple else FieldType.RADIO,
                            "multiple": field.multiple,
                        }
                    )
                parsed.append(field)
            elif isinstance(field, dict):
                # 从字典创建 FormField。带 options 的字段可省略 type。
                field_multiple = bool(field.get("multiple", False))
                field_type = field.get("type")
                if not field_type:
                    field_type = (
                        "multi_select"
                        if field.get("options") and field_multiple
                        else "radio"
                        if field.get("options")
                        else "text"
                    )
                if isinstance(field_type, str):
                    type_aliases = {
                        "choice": "radio",
                        "single": "radio",
                        "single_select": "radio",
                        "multiple_choice": "multi_select",
                        "checkbox_group": "multi_select",
                    }
                    field_type = FieldType(type_aliases.get(field_type, field_type))

                # 兼容 LLM 可能使用 "id" 而不是 "name" 的情况
                field_name = field.get("name") or field.get("id") or "choice"

                form_field = FormField(
                    name=field_name,
                    label=field.get("label")
                    or field.get("title")
                    or ("请选择" if field.get("options") else field_name),
                    type=field_type,
                    placeholder=field.get("placeholder"),
                    default=field.get("default", self._get_type_default(field_type)),
                    required=field.get("required", True),
                    options=field.get("options"),
                    multiple=field_multiple or field_type == FieldType.MULTI_SELECT,
                )
                parsed.append(form_field)
            else:
                logger.warning(f"Unknown field type: {type(field)}")

        # 如果没有字段，添加一个默认的文本字段
        if not parsed:
            parsed.append(
                FormField(
                    name="response",
                    label="响应",
                    type=FieldType.TEXT,
                    required=True,
                )
            )

        return parsed

    def _get_type_default(self, field_type: FieldType) -> Any:
        """
        获取字段类型的默认值

        Args:
            field_type: 字段类型

        Returns:
            该类型的默认值
        """
        defaults = {
            FieldType.TEXT: "",
            FieldType.TEXTAREA: "",
            FieldType.NUMBER: 0,
            FieldType.CHECKBOX: False,
            FieldType.SELECT: None,
            FieldType.RADIO: None,
            FieldType.MULTI_SELECT: [],
        }
        return defaults.get(field_type, None)

    def _get_default_values(self, fields: List[FormField]) -> Dict[str, Any]:
        """
        获取所有字段的默认值

        Args:
            fields: 字段列表

        Returns:
            字段名到默认值的映射
        """
        values = {}
        for field in fields:
            if field.default is not None:
                values[field.name] = field.default
            else:
                values[field.name] = self._get_type_default(field.type)
        return values

    async def _send_approval_event(
        self,
        approval,
        session_id: Optional[str],
        run_id: Optional[str],
        fields: List[FormField],
        timeout: int = 300,
    ) -> None:
        """
        发送 approval_required 事件到 SSE 流

        Args:
            approval: 审批对象
            session_id: 会话 ID
            run_id: 运行 ID
            fields: 表单字段列表
        """
        logger.info(
            f"[AskHuman] _send_approval_event called: session_id={session_id}, "
            f"run_id={run_id}, approval_id={approval.id}"
        )

        if not session_id:
            logger.warning("[AskHuman] Cannot send approval event: no session_id")
            return

        try:
            from src.infra.session.dual_writer import get_dual_writer

            dual_writer = get_dual_writer()
            logger.info(
                f"[AskHuman] Writing approval_required event to Redis: "
                f"session={session_id}, run_id={run_id}"
            )

            # 构建事件数据
            event_data = {
                "id": approval.id,
                "message": approval.message,
                "type": approval.type,
                "fields": [f.model_dump() for f in fields],
                "timeout": timeout,
            }

            await dual_writer.write_event(
                session_id=session_id,
                event_type="approval_required",
                data=event_data,
                run_id=run_id,
            )
            logger.info(
                f"[AskHuman] Sent approval_required event: approval_id={approval.id}, "
                f"session={session_id}, run_id={run_id}"
            )
        except Exception as e:
            logger.error(f"[AskHuman] Failed to send approval event: {e}", exc_info=True)


def get_human_tool(session_id: str = "") -> AskHumanTool:
    """
    获取 ask_human 工具实例

    Args:
        session_id: 会话 ID，用于关联审批请求（可选，优先使用 TraceContext）

    Returns:
        配置好的 AskHumanTool 实例
    """
    return AskHumanTool(session_id=session_id)
