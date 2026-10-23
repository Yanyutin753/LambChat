"""
Quick Agent 节点 - 快问快答：消息直发 LLM

不直接执行工具、技能或沙箱；仅提供内部 Search 接力动作。流式回复不经过 deepagents：
节点把 LLM 调用挂在节点 config 上，外层图 astream_events 捕获
on_chat_model_stream/on_chat_model_end，由 BaseGraphAgent._stream 的
AgentEventProcessor 统一转成 message:chunk 与 token:usage 事件。
"""

from typing import Any, Dict
from uuid import uuid4

from langchain_core.messages import SystemMessage
from langchain_core.runnables import RunnableConfig

from src.agents.core.node_utils import (
    build_human_message,
    inline_image_attachments_as_data_urls,
    resolve_fallback_model,
    resolve_model_image_url_mode,
    resolve_model_supports_vision,
)
from src.agents.core.subagent_prompts import build_response_language_section
from src.agents.core.thinking import build_thinking_config
from src.agents.quick_agent.prompt import QUICK_SYSTEM_PROMPT, SEARCH_HANDOFF_TOOL
from src.infra.agent.middleware.image_url import prepare_image_messages
from src.infra.agent.middleware.subagent_activity import ActivityReferenceMiddleware
from src.infra.llm.client import LLMClient
from src.infra.llm.retry import ainvoke_with_retry
from src.infra.logging import get_logger
from src.kernel.errors import AppError, ErrorCode

logger = get_logger(__name__)

_PERSONA_HEADING = "## Persona"


def _build_system_prompt(configurable: Dict[str, Any]) -> str:
    """基础提示 + 可选 persona 段 + 可选回复语言段。"""
    sections: list[str] = [QUICK_SYSTEM_PROMPT]

    persona_prompt = (configurable.get("persona_system_prompt") or "").strip()
    if persona_prompt:
        sections.append(f"{_PERSONA_HEADING}\n\n{persona_prompt}")

    agent_options = configurable.get("agent_options") or {}
    language_section = build_response_language_section(agent_options.get("response_language"))
    if language_section:
        sections.append(language_section)

    return "\n\n".join(sections)


def _extract_text(content: Any) -> str:
    """从 AIMessage.content 提取纯文本（兼容 str 与内容块列表）。"""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(
            block.get("text", "")
            for block in content
            if isinstance(block, dict) and block.get("type") == "text"
        )
    return str(content)


async def quick_agent_node(state: Dict[str, Any], config: RunnableConfig) -> Dict[str, Any]:
    """
    Quick Agent 主节点 - 消息直发 LLM，单轮问答

    历史由外层图的 messages channel（add_messages + checkpointer）维护，
    节点只负责本轮：系统提示 + 历史 + 新消息 -> LLM -> 追加回复。
    """
    configurable = config.get("configurable", {})
    agent_options = configurable.get("agent_options") or {}

    context = configurable.get("context")
    user_id = getattr(context, "user_id", None)
    session_id = str(state.get("session_id") or "")
    thinking = build_thinking_config(agent_options)
    llm = await LLMClient.get_model(
        model=agent_options.get("model"),
        model_id=agent_options.get("model_id"),
        model_config=agent_options.get("_resolved_model_config"),
        thinking=thinking,
    )

    user_input = state.get("input", "")
    attachments = state.get("attachments") or []
    supports_vision = False
    if attachments:
        supports_vision = await resolve_model_supports_vision(
            agent_options.get("model_id"),
            agent_options.get("model"),
            log_prefix="[QuickAgent]",
        )
        if supports_vision:
            attachments = await inline_image_attachments_as_data_urls(
                attachments,
                base_url=configurable.get("base_url", ""),
                user_id=user_id,
                session_id=session_id,
            )
    human_message = build_human_message(user_input, attachments, supports_vision=supports_vision)

    messages = [
        SystemMessage(content=_build_system_prompt(configurable)),
        *state.get("messages", []),
        human_message,
    ]

    # Historical images need refreshed authorization too; never write capabilities to state.
    image_mode = agent_options.get("_resolved_image_url_mode")
    if image_mode is None and any(isinstance(message.content, list) for message in messages):
        image_mode = await resolve_model_image_url_mode(
            agent_options.get("model_id"), agent_options.get("model"), log_prefix="[QuickAgent]"
        )
    original_messages = messages
    messages = await prepare_image_messages(
        original_messages,
        mode=image_mode,
        user_id=user_id,
        session_id=session_id,
        base_url=configurable.get("base_url", ""),
    )

    fallback = agent_options.get("_resolved_fallback_model")
    if "_resolved_fallback_model" not in agent_options:
        fallback = await resolve_fallback_model(
            agent_options.get("model_id"), agent_options.get("model"), log_prefix="[QuickAgent]"
        )

    async def prepare_fallback_prompt(model_reference: str):
        mode = await resolve_model_image_url_mode(None, model_reference, log_prefix="[QuickAgent]")
        return await prepare_image_messages(
            original_messages,
            mode=mode,
            user_id=user_id,
            session_id=session_id,
            base_url=configurable.get("base_url", ""),
        )

    ai_message = await ainvoke_with_retry(
        llm,
        messages,
        config=config,
        operation="quick-agent",
        fallback_model=fallback,
        prepare_fallback_prompt=prepare_fallback_prompt,
        thinking=thinking,
        tools=[SEARCH_HANDOFF_TOOL] if configurable.get("allow_search_handoff") else None,
    )

    ai_message = ActivityReferenceMiddleware._strip_model_references(ai_message)

    if configurable.get("allow_search_handoff") and any(
        call.get("name") == "handoff_to_search" for call in ai_message.tool_calls
    ):
        # Commit the request before changing executors; Search reuses this ID to deduplicate.
        presenter = configurable.get("presenter")
        human_message.id = f"handoff-user:{presenter.run_id if presenter else uuid4().hex}"
        return {
            "messages": [human_message],
            "output": "",
            "agent_handoff": {"agent_id": "search", "message_id": human_message.id},
        }

    if ai_message.tool_calls:
        raise AppError(ErrorCode.INTERNAL_ERROR)

    return {
        "messages": [human_message, ai_message],
        "output": _extract_text(ai_message.content),
        "agent_handoff": None,
    }
