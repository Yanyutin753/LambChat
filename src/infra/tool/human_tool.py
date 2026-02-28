"""
Human Input 工具

让 Agent 可以在遇到不确定情况时请求人工输入。
"""

import logging
from enum import Enum
from typing import Optional, Type

from langchain_core.tools import BaseTool
from pydantic import BaseModel, Field, field_validator

from src.api.routes.human import create_approval, wait_for_response

logger = logging.getLogger(__name__)


class QuestionType(str, Enum):
    """问题类型枚举"""

    TEXT = "text"
    CONFIRM = "confirm"
    CHOICE = "choice"

    def __str__(self) -> str:
        return self.value


class AskHumanInput(BaseModel):
    """ask_human 工具的输入参数"""

    question: str = Field(
        ...,
        description="向用户提出的问题",
    )
    question_type: QuestionType = Field(
        default=QuestionType.TEXT,
        description="问题类型：text（文本输入）、confirm（确认）、choice（多选一）",
    )
    choices: Optional[str] = Field(
        default=None,
        description="选项列表（仅 question_type=choice 时使用，用逗号分隔）",
    )
    default: Optional[str] = Field(
        default=None,
        description="默认值（用户未响应时使用）",
    )
    timeout: int = Field(
        default=300,
        ge=10,
        le=3600,
        description="等待响应的超时时间（秒）",
    )

    @field_validator("choices")
    @classmethod
    def parse_choices(cls, v: Optional[str]) -> Optional[list[str]]:
        """解析 choices 为列表"""
        if v:
            return [c.strip() for c in v.split(",")]
        return None


class AskHumanTool(BaseTool):
    """
    请求人工输入的工具

    当 Agent 遇到不确定的情况时，可以调用此工具请求人工输入。
    工具会阻塞直到用户响应或超时。

    使用场景：
    - 需要用户确认敏感操作
    - 需要用户提供额外信息
    - 遇到多种可能的方案需要用户选择
    - 不确定用户意图时请求澄清
    """

    name: str = "ask_human"
    description: str = """当遇到不确定的情况时，向用户提问并等待响应。

使用场景：
- 需要用户确认敏感操作（如删除文件、执行危险命令）
- 需要用户提供额外信息才能继续
- 遇到多种可能的方案需要用户选择
- 不确定用户意图时请求澄清

参数：
- question: 向用户提出的问题
- question_type: 问题类型 - text（文本输入）、confirm（是/否确认）、choice（多选一）
- choices: 当类型为 choice 时，用逗号分隔的选项，如 "选项A,选项B,选项C"
- default: 默认值
- timeout: 超时时间（秒）

示例：
- 确认删除：ask_human(question="确定要删除这个文件吗？", question_type="confirm")
- 获取输入：ask_human(question="请输入数据库连接字符串", question_type="text")
- 多选一：ask_human(question="选择部署环境", question_type="choice", choices="开发,测试,生产")
"""
    args_schema: Type[BaseModel] = AskHumanInput
    return_direct: bool = False

    # 从 context 注入（可选，优先使用 TraceContext）
    session_id: str = ""

    def _run(
        self,
        question: str,
        question_type: QuestionType = QuestionType.TEXT,
        choices: Optional[str] = None,
        default: Optional[str] = None,
        timeout: int = 300,
    ) -> str:
        """同步执行（不支持，返回提示）"""
        return "Error: ask_human only supports async execution. Use ainvoke instead."

    async def _arun(
        self,
        question: str,
        question_type: QuestionType = QuestionType.TEXT,
        choices: Optional[str] = None,
        default: Optional[str] = None,
        timeout: int = 300,
    ) -> str:
        """
        异步执行：创建审批请求并等待响应

        Args:
            question: 向用户提出的问题
            question_type: 问题类型 - text（文本输入）、confirm（确认）、choice（选择）
            choices: 当类型为 choice 时，用逗号分隔的选项
            default: 默认值（超时或用户未输入时使用）
            timeout: 超时时间（秒），范围 10-3600

        Returns:
            用户的响应内容，或超时/拒绝的错误消息
        """
        # 解析选项
        choices_list: Optional[list[str]] = None
        if question_type == QuestionType.CHOICE and choices:
            choices_list = [c.strip() for c in choices.split(",")]
            # 如果没有设置默认值，默认使用第一个选项
            if not default and choices_list:
                default = choices_list[0]

        # confirm 类型设置默认值
        if question_type == QuestionType.CONFIRM and default is None:
            default = "false"

        # 获取当前请求上下文
        from src.infra.logging.context import TraceContext

        ctx = TraceContext.get_request_context()
        session_id = self.session_id or ctx.session_id
        run_id = ctx.run_id

        # 创建审批请求
        approval = await create_approval(
            message=question,
            approval_type=question_type.value,
            choices=choices_list,
            default=default,
            session_id=session_id or None,
        )

        # 通过 SSE 流发送 approval_required 事件，让前端立即知道需要响应
        await self._send_approval_event(approval, session_id, run_id)

        # 等待用户响应
        response = await wait_for_response(approval.id, timeout=timeout)

        if response is None:
            # 超时：如果有默认值，使用默认值；否则返回超时消息
            if default is not None:
                return f"等待用户响应超时，已使用默认值：{default}"
            return f"等待用户响应超时（{timeout}秒）。请重新表述你的问题或尝试其他方案。"

        if not response.approved:
            return "用户拒绝了此请求。请考虑其他方案或询问用户需要什么帮助。"

        # 返回用户的响应
        return response.response or "用户确认继续。"

    async def _send_approval_event(
        self, approval, session_id: Optional[str], run_id: Optional[str]
    ) -> None:
        """发送 approval_required 事件到 SSE 流"""
        logger.info(
            f"[AskHuman] _send_approval_event called: session_id={session_id}, run_id={run_id}, approval_id={approval.id}"
        )

        if not session_id:
            logger.warning("[AskHuman] Cannot send approval event: no session_id")
            return

        try:
            from src.infra.session.dual_writer import get_dual_writer

            dual_writer = get_dual_writer()
            logger.info(
                f"[AskHuman] Writing approval_required event to Redis: session={session_id}, run_id={run_id}"
            )
            await dual_writer.write_event(
                session_id=session_id,
                event_type="approval_required",
                data={
                    "id": approval.id,
                    "message": approval.message,
                    "type": approval.type,
                    "choices": approval.choices,
                    "default": approval.default,
                },
                run_id=run_id,
            )
            logger.info(
                f"[AskHuman] Sent approval_required event: approval_id={approval.id}, session={session_id}, run_id={run_id}"
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
