"""
Human Tool 实现

支持多字段表单的 ask_human 工具的 LangChain 工具实现。
"""

import json
from typing import Any, Dict, List, Optional, Type

from langchain_core.tools import BaseTool

from src.api.routes.human import create_approval, wait_for_response
from src.infra.logging import get_logger
from src.infra.tool.human_tool.models import AskHumanInput, FieldType, FormField

logger = get_logger(__name__)


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
    description: str = """向用户提问并等待响应，支持多字段表单。

使用场景：
- 需要用户确认敏感操作（如删除文件、执行危险命令）
- 需要用户提供额外信息才能继续
- 需要用户填写表单（如数据库连接信息、配置参数等）
- 遇到多种可能的方案需要用户选择
- 不确定用户意图时请求澄清

参数：
- message: 向用户展示的提示消息，说明需要用户提供什么信息
- fields: 表单字段列表，每个字段包含：
  - name: 字段名称（用于标识返回值）
  - label: 显示给用户的标签
  - type: 字段类型 - text（单行文本）、textarea（多行文本）、number（数字）、checkbox（复选框）、select（下拉单选）、multi_select（下拉多选）
  - placeholder: 输入框占位符文本（可选）
  - default: 默认值（可选）
  - required: 是否必填（默认 true）
  - options: 选项列表（仅 select 和 multi_select 类型使用）
- timeout: 等待响应的超时时间（秒），范围 10-3600，默认 300
- allow_other: 是否额外提供「其他意见」文本输入框（默认 false），启用后返回值中会包含 other 字段

返回值：
- 成功时返回 JSON 字符串，包含各字段的值
- 超时时返回超时消息
- 用户拒绝时返回拒绝消息

示例：
1. 简单确认：
   ask_human(message="确定要删除这个文件吗？", fields=[{"name": "confirm", "label": "确认", "type": "checkbox", "default": false}])

2. 获取文本输入：
   ask_human(message="请输入数据库连接信息", fields=[
     {"name": "host", "label": "主机地址", "type": "text", "required": true},
     {"name": "port", "label": "端口", "type": "number", "default": 5432},
     {"name": "password", "label": "密码", "type": "text", "required": true}
   ])

3. 多选一：
   ask_human(message="选择部署环境", fields=[
     {"name": "env", "label": "环境", "type": "select", "options": ["development", "staging", "production"], "default": "development"}
   ])

4. 多行文本：
   ask_human(message="请描述问题详情", fields=[
     {"name": "description", "label": "描述", "type": "textarea", "placeholder": "请详细描述您遇到的问题..."}
   ])
"""
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
        if fields is None:
            fields = []

        # 解析字段并设置默认值
        parsed_fields = self._parse_fields(fields)

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
        )

        # 通过 SSE 流发送 approval_required 事件
        await self._send_approval_event(approval, session_id, run_id, parsed_fields)

        # 等待用户响应
        response = await wait_for_response(approval.id, timeout=timeout)

        if response is None:
            # 超时：构建超时响应
            result = {
                "status": "timeout",
                "message": f"等待用户响应超时（{timeout}秒）",
                "values": self._get_default_values(parsed_fields),
            }
            return json.dumps(result, ensure_ascii=False)

        if not response.approved:
            # 用户拒绝
            result = {
                "status": "rejected",
                "message": "用户拒绝了此请求",
                "values": {},
            }
            return json.dumps(result, ensure_ascii=False)

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
        return json.dumps(result, ensure_ascii=False)

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
                parsed.append(field)
            elif isinstance(field, dict):
                # 从字典创建 FormField
                field_type = field.get("type", "text")
                if isinstance(field_type, str):
                    field_type = FieldType(field_type)

                # 兼容 LLM 可能使用 "id" 而不是 "name" 的情况
                field_name = field.get("name") or field.get("id", "")

                form_field = FormField(
                    name=field_name,
                    label=field.get("label", field_name),
                    type=field_type,
                    placeholder=field.get("placeholder"),
                    default=field.get("default", self._get_type_default(field_type)),
                    required=field.get("required", True),
                    options=field.get("options"),
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
                "timeout": 300,  # 可以从参数传入
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
