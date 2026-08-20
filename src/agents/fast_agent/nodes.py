"""
Fast Agent 节点 - 无沙箱，快速响应

基于 deep_agent/nodes.py 简化，移除沙箱相关逻辑。
"""

import inspect
import time
import uuid
from typing import Any, Dict

from deepagents import create_deep_agent
from deepagents.middleware.subagents import CompiledSubAgent, SubAgent
from langchain_core.runnables import RunnableConfig

from src.agents.core.base import get_presenter
from src.agents.core.node_utils import (
    build_human_message,
    build_nested_graph_configurable,
    emit_token_usage,
    inline_image_attachments_as_data_urls,
    isolated_nested_graph_run,
    resolve_fallback_model,
    resolve_model_image_url_to_base64,
    resolve_model_supports_vision,
)
from src.agents.core.persona import build_persona_prompt_sections
from src.agents.core.startup_preparation import prepare_agent_inputs
from src.agents.core.subagent_prompts import (
    CODEBASE_INVESTIGATOR_PROMPT,
    IMPLEMENTATION_WORKER_PROMPT,
    MAIN_AGENT_PROMPT_SECTIONS,
    RESEARCH_SUBAGENT_PROMPT,
    SPECIALIZED_SUBAGENT_DESCRIPTIONS,
    SUBAGENT_PROMPT,
    VERIFICATION_RUNNER_PROMPT,
    get_memory_guide,
)
from src.agents.core.thinking import build_thinking_config
from src.agents.fast_agent.context import FastAgentContext
from src.agents.fast_agent.prompt import FAST_SYSTEM_PROMPT
from src.infra.agent import AgentEventProcessor
from src.infra.agent.middleware import (
    ArtifactDeliveryMiddleware,
    ImageUrlToBase64Middleware,
    MainAgentContextMiddleware,
    SectionPromptMiddleware,
    SubagentActivityMiddleware,
    SubagentResultHandoffMiddleware,
    ToolResultBinaryMiddleware,
    create_code_interpreter_middleware,
    create_retry_middleware,
    summarization_fallback_patch,
)
from src.infra.backend.deepagent import create_persistent_backend
from src.infra.goal import (
    build_goal_input,
    create_goal_rubric_middleware,
)
from src.infra.llm.client import LLMClient
from src.infra.logging import get_logger
from src.infra.storage.checkpoint import get_async_checkpointer
from src.infra.storage.mongodb_store import acreate_store
from src.kernel.config import settings

logger = get_logger(__name__)


# ============================================================================
# 节点函数
# ============================================================================


async def fast_agent_node(state: Dict[str, Any], config: RunnableConfig) -> Dict[str, Any]:
    """
    Fast Agent 主节点 - 无沙箱，快速响应

    特点：
    - 不使用沙箱（直接使用内存 backend）
    - 支持技能（Skills）
    - 支持长期存储（可选）
    - 流式输出
    """
    start_time = time.time()

    presenter = get_presenter(config)
    configurable = config.get("configurable", {})
    context: FastAgentContext = configurable.get("context", FastAgentContext())

    # 获取 agent_options
    agent_options = configurable.get("agent_options") or {}
    selected_model = agent_options.get("model")  # Per-request model override
    model_id = agent_options.get("model_id")  # Model config ID for specific channel/provider
    resolved_model_config = agent_options.get("_resolved_model_config")
    thinking_config = build_thinking_config(agent_options)

    # 获取附件
    attachments = state.get("attachments", [])

    # 多租户隔离
    tenant_id = context.user_id or "default"
    assistant_id = f"assistant-{tenant_id}"

    # 构建 persona + skills 提示
    persona_sections = build_persona_prompt_sections(configurable.get("persona_system_prompt"))

    # 构建记忆系统提示
    memory_guide = get_memory_guide() if settings.ENABLE_MEMORY else ""

    # 构建系统提示（persona 由 SectionPromptMiddleware 注入）
    system_prompt = FAST_SYSTEM_PROMPT

    session_id = state.get("session_id", str(uuid.uuid4()))

    async def _load_model_bundle() -> tuple[Any, Any, bool, bool]:
        llm_start = time.time()
        model = await LLMClient.get_model(
            model=selected_model,
            model_id=model_id,
            model_config=resolved_model_config,
            thinking=thinking_config,
        )
        logger.debug(f"[FastAgent] LLM init: {(time.time() - llm_start) * 1000:.3f}ms")
        fallback = agent_options.get("_resolved_fallback_model")
        if "_resolved_fallback_model" not in agent_options:
            fallback = await resolve_fallback_model(
                model_id, selected_model, log_prefix="[FastAgent]"
            )
        vision = agent_options.get("_resolved_supports_vision")
        if vision is None:
            vision = await resolve_model_supports_vision(
                model_id, selected_model, log_prefix="[FastAgent]"
            )
        convert_images = agent_options.get("_resolved_image_url_to_base64")
        if convert_images is None:
            convert_images = await resolve_model_image_url_to_base64(
                model_id, selected_model, log_prefix="[FastAgent]"
            )
        return model, fallback, bool(vision), bool(convert_images)

    async def _load_backend_bundle() -> tuple[Any, Any]:
        backend_start = time.time()
        loaded_backend = create_persistent_backend(
            assistant_id=assistant_id,
            user_id=context.user_id,
            session_id=session_id,
        )
        logger.info(f"[FastAgent] Using PersistentBackend for assistant: {assistant_id}")
        loaded_store = await acreate_store()
        logger.debug(f"[FastAgent] Backend init: {(time.time() - backend_start) * 1000:.3f}ms")
        return loaded_backend, loaded_store

    async def _load_context_tools() -> list[Any]:
        get_tools = getattr(context, "get_tools", None)
        if callable(get_tools):
            maybe_tools = get_tools()
            if inspect.isawaitable(maybe_tools):
                await maybe_tools
        filter_tools = getattr(context, "filter_tools", None)
        return list(filter_tools() if callable(filter_tools) else getattr(context, "tools", []))

    prepared = await prepare_agent_inputs(
        model=_load_model_bundle(),
        backend=_load_backend_bundle(),
        tools=_load_context_tools(),
        checkpointer=get_async_checkpointer(thread_id=state.get("session_id")),
    )
    llm, fallback_model_value, supports_vision, image_url_to_base64 = prepared.model
    backend, store = prepared.backend
    filtered_tool_list = prepared.tools
    inner_checkpointer = prepared.checkpointer

    if context.deferred_manager is not None and not any(
        getattr(tool, "name", "") == "search_tools" for tool in filtered_tool_list
    ):
        from src.infra.tool.tool_search_tool import ToolSearchTool

        filtered_tool_list.append(
            ToolSearchTool(
                manager=context.deferred_manager,
                search_limit=settings.DEFERRED_TOOL_SEARCH_LIMIT,
            )
        )
    filtered_tools: list[Any] | None = filtered_tool_list or None

    # Diagnostic: log tool names passed to the LLM
    if filtered_tools is not None:
        tool_names = [getattr(t, "name", str(t)) for t in filtered_tools]
        has_sched = any("scheduled_task" in n for n in tool_names)
        logger.info(
            "[FastAgent] Passing %d tools to create_deep_agent (scheduled_task=%s): %s",
            len(filtered_tools),
            has_sched,
            tool_names,
        )
    else:
        logger.warning("[FastAgent] filtered_tools is None — no tools will be passed to LLM!")

    graph_compile_start = time.time()

    # 自定义子代理配置 - 强制将所有中间信息保存到文件
    subagent_base_url = configurable.get("base_url", "")
    subagent_prompt_sections = [s for s in (*persona_sections, memory_guide) if s]

    def _build_subagent_middleware(subagent_type: str) -> list:
        mw = [
            *create_retry_middleware(fallback_model=fallback_model_value, thinking=thinking_config),
            ToolResultBinaryMiddleware(base_url=subagent_base_url),
            ArtifactDeliveryMiddleware(),
            SubagentActivityMiddleware(backend=backend),
        ]
        if image_url_to_base64:
            mw.append(ImageUrlToBase64Middleware())
        if subagent_prompt_sections:
            mw.append(SectionPromptMiddleware(sections=subagent_prompt_sections))
        if context.deferred_manager is not None:
            from src.infra.agent.middleware import ToolSearchMiddleware

            subagent_deferred_manager = context.deferred_manager.fork_for_scope(
                f"subagent:{subagent_type}"
            )
            mw.append(
                ToolSearchMiddleware(
                    deferred_manager=subagent_deferred_manager,
                    search_limit=settings.DEFERRED_TOOL_SEARCH_LIMIT,
                )
            )
        return mw

    custom_subagents: list[SubAgent | CompiledSubAgent] = [
        {
            "name": "general-purpose",
            "description": "General-purpose agent for researching complex questions, searching for files and content, and executing multi-step tasks. When you are searching for a keyword or file and are not confident that you will find the right match in the first few tries use this agent to perform the search for you. This agent has access to all tools as the main agent.",
            "system_prompt": SUBAGENT_PROMPT,
            "middleware": _build_subagent_middleware("general-purpose"),
        },
        {
            "name": "codebase-investigator",
            "description": SPECIALIZED_SUBAGENT_DESCRIPTIONS["codebase-investigator"],
            "system_prompt": CODEBASE_INVESTIGATOR_PROMPT,
            "middleware": _build_subagent_middleware("codebase-investigator"),
        },
        {
            "name": "implementation-worker",
            "description": SPECIALIZED_SUBAGENT_DESCRIPTIONS["implementation-worker"],
            "system_prompt": IMPLEMENTATION_WORKER_PROMPT,
            "middleware": _build_subagent_middleware("implementation-worker"),
        },
        {
            "name": "verification-runner",
            "description": SPECIALIZED_SUBAGENT_DESCRIPTIONS["verification-runner"],
            "system_prompt": VERIFICATION_RUNNER_PROMPT,
            "middleware": _build_subagent_middleware("verification-runner"),
        },
        {
            "name": "researcher",
            "description": SPECIALIZED_SUBAGENT_DESCRIPTIONS["researcher"],
            "system_prompt": RESEARCH_SUBAGENT_PROMPT,
            "middleware": _build_subagent_middleware("researcher"),
        },
    ]

    # 构建中间件栈：retry → binary upload → authored prompts → memory_index → tool search
    user_middleware = create_retry_middleware(
        fallback_model=fallback_model_value, thinking=thinking_config
    )
    user_middleware.append(ToolResultBinaryMiddleware(base_url=subagent_base_url))
    user_middleware.append(ArtifactDeliveryMiddleware())
    if image_url_to_base64:
        user_middleware.append(ImageUrlToBase64Middleware())
    active_goal = configurable.get("active_goal")
    # Persona, skills, memory guidance, goal, and mode share one authored prompt block.
    _prompt_sections = [
        s for s in (*MAIN_AGENT_PROMPT_SECTIONS, *persona_sections, memory_guide) if s
    ]
    if _prompt_sections:
        user_middleware.append(SectionPromptMiddleware(sections=_prompt_sections))
    if settings.ENABLE_MEMORY and settings.NATIVE_MEMORY_INDEX_ENABLED and context.user_id:
        from src.infra.agent.middleware import MemoryIndexMiddleware

        user_middleware.append(MemoryIndexMiddleware(user_id=context.user_id))

    if context.deferred_manager is not None:
        from src.infra.agent.middleware import ToolSearchMiddleware

        user_middleware.append(
            ToolSearchMiddleware(
                deferred_manager=context.deferred_manager,
                search_limit=settings.DEFERRED_TOOL_SEARCH_LIMIT,
            )
        )

    user_middleware.extend(create_code_interpreter_middleware(agent_options))
    rubric_middleware = create_goal_rubric_middleware(
        model=llm,
        goal=active_goal,
        fallback_model=fallback_model_value,
        thinking=thinking_config,
    )
    if rubric_middleware is not None:
        user_middleware.append(rubric_middleware)

    user_middleware.append(MainAgentContextMiddleware(backend=backend))
    user_middleware.append(SubagentResultHandoffMiddleware(backend=backend))

    with summarization_fallback_patch(fallback_model_value, thinking_config):
        inner_graph = create_deep_agent(
            model=llm,
            system_prompt=system_prompt,
            backend=backend,
            tools=filtered_tools,
            checkpointer=inner_checkpointer,
            store=store,
            skills=None,
            subagents=custom_subagents,
            middleware=user_middleware,
        )
    graph_compile_time = time.time() - graph_compile_start
    logger.debug(f"[FastAgent] Graph compile: {graph_compile_time * 1000:.3f}ms")

    inner_config: RunnableConfig = {
        "configurable": build_nested_graph_configurable(
            thread_id=state.get("session_id", str(uuid.uuid4())),
            checkpointer=inner_checkpointer,
            backend=backend,
            context=context,
            disabled_skills=configurable.get("disabled_skills"),
            enabled_skills=configurable.get("enabled_skills"),
            base_url=configurable.get("base_url", ""),
            session_id=state.get("session_id"),
            trace_id=getattr(presenter, "trace_id", None),
            presenter=presenter,  # 传递 presenter 给工具调用
            attachments=attachments,
        ),
        "recursion_limit": config.get("recursion_limit", settings.SESSION_MAX_RUNS_PER_SESSION),
    }

    # 构建传入的新消息（包含附件）
    # 注意：checkpointer + add_messages reducer 会自动维护历史消息，
    # 只需传入新消息，避免与 checkpoint 中的历史消息重复。
    # HITL 恢复运行（issue #218）：以 Command(resume=...) 从挂起断点继续，
    # 不注入新的用户消息。
    hitl_resume = configurable.get("hitl_resume")
    user_input = state.get("input", "")
    recommendation_input = configurable.get("recommendation_input") or user_input
    if hitl_resume is not None:
        from langgraph.types import Command

        graph_input: Any = Command(resume=hitl_resume.get("resume_value"))
    else:
        if supports_vision:
            attachments = await inline_image_attachments_as_data_urls(
                attachments,
                base_url=configurable.get("base_url", ""),
                force_data_url=image_url_to_base64,
            )
        new_message = build_human_message(
            user_input, attachments, supports_vision=supports_vision
        )
        graph_input = build_goal_input(
            new_message, active_goal, rubric_middleware=rubric_middleware
        )

    # 创建事件处理器（使用 AgentEventProcessor 处理 astream_events）
    logger.info("[FastAgent] Creating AgentEventProcessor")
    event_processor = AgentEventProcessor(presenter, base_url=configurable.get("base_url", ""))

    logger.info("[FastAgent] Starting astream_events")
    # 流式处理事件（不重试，直接调用）
    # interrupt 模式仅在持久 checkpointer（非 MemorySaver）可用时启用，
    # 否则 ask_human 自动回退阻塞模式。
    from langgraph.checkpoint.memory import MemorySaver

    from src.infra.tool.human_tool.runtime import hitl_interrupt_supported

    interrupt_supported = (
        getattr(settings, "HITL_MODE", "blocking") == "interrupt"
        and inner_checkpointer is not None
        and not isinstance(inner_checkpointer, MemorySaver)
    )
    try:
        async with isolated_nested_graph_run():
            token_supported = hitl_interrupt_supported.set(interrupt_supported)
            try:
                async for event in inner_graph.astream_events(  # type: ignore[call-overload]
                    graph_input,
                    inner_config,
                    version="v2",
                ):
                    await event_processor.process_event(event)
            finally:
                hitl_interrupt_supported.reset(token_supported)
    finally:
        await event_processor.flush()
        await emit_token_usage(
            event_processor,
            presenter,
            start_time,
            model_id=model_id,
            model=selected_model,
        )
    logger.info("[FastAgent] astream_events completed")

    # 检测 interrupt 挂起（issue #218）：图存在待恢复任务时标记 WAITING_HUMAN，
    # 并将 ask_human interrupt payload 物化为审批记录 + SSE 通知
    # （工具内零副作用，对齐 deepagents 官方 HITL，重放不会重复创建）
    if interrupt_supported:
        try:
            snapshot = await inner_graph.aget_state(inner_config)  # type: ignore[attr-defined]
            if snapshot is not None and snapshot.next:
                presenter.hitl_suspended = True
                logger.info(
                    "[FastAgent] Graph suspended by interrupt: session=%s run_id=%s",
                    state.get("session_id"),
                    getattr(presenter, "run_id", None),
                )
                from src.infra.logging.context import TraceContext
                from src.infra.task.hitl import materialize_ask_human_approvals

                ctx = TraceContext.get_request_context()
                await materialize_ask_human_approvals(
                    snapshot,
                    session_id=state.get("session_id"),
                    run_id=getattr(presenter, "run_id", None) or ctx.run_id,
                    user_id=context.user_id or ctx.user_id,
                )
        except Exception as e:
            logger.warning("[FastAgent] Failed to inspect graph state after run: %s", e)

    if settings.ENABLE_MEMORY and context.user_id and hitl_resume is None:
        from src.infra.logging.context import TraceContext
        from src.infra.memory.tools import schedule_auto_memory_capture
        from src.kernel.schemas.conversation_history import ConversationSourceRef

        request_context = TraceContext.get_request_context()
        source_refs = (
            [
                ConversationSourceRef(
                    session_id=request_context.session_id,
                    run_id=request_context.run_id,
                )
            ]
            if request_context.session_id and request_context.run_id
            else None
        )
        schedule_auto_memory_capture(context.user_id, user_input, source_refs=source_refs)

    session_id = state.get("session_id")
    if (
        context.deferred_manager is not None
        and session_id
        and context.deferred_manager.discovered_count > 0
    ):
        try:
            from src.infra.tool.deferred_manager import persist_discovered_tools

            await persist_discovered_tools(
                session_id,
                context.deferred_manager.discovered_names,
            )
        except Exception as e:
            logger.warning("持久化已发现工具失败 (fast_agent): %s", e, exc_info=True)

    output_text = event_processor.output_text
    event_processor.clear()

    if recommendation_input and settings.ENABLE_RECOMMEND_QUESTIONS and hitl_resume is None:
        try:
            from src.agents.core.recommendations import schedule_recommend_questions_from_state

            schedule_recommend_questions_from_state(
                presenter,
                recommendation_input,
                output_text,
                inner_graph,
                inner_config,
            )
        except Exception as exc:
            logger.debug("Failed to schedule recommended questions: %s", exc)

    return {
        "output": output_text,
    }
