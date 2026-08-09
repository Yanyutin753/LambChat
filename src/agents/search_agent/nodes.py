"""
Search Agent 节点

LangGraph 节点函数，使用 deep agent 执行任务。
后续可扩展：retrieve_node, summarize_node 等。
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
from src.agents.core.subagent_prompts import (
    AUTO_MODE_PROMPT_SECTION,
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
from src.agents.core.todo_middleware import create_todo_middleware
from src.agents.search_agent.context import SearchAgentContext
from src.agents.search_agent.prompt import (
    DEFAULT_SYSTEM_PROMPT,
    SANDBOX_RUNTIME_SECTION,
    SANDBOX_SYSTEM_PROMPT,
)
from src.infra.agent import AgentEventProcessor
from src.infra.agent.middleware import (
    ArtifactDeliveryMiddleware,
    EnvVarPromptMiddleware,
    ImageUrlToBase64Middleware,
    MainAgentContextMiddleware,
    PromptCachingMiddleware,
    SectionPromptMiddleware,
    SubagentActivityMiddleware,
    SubagentResultHandoffMiddleware,
    ToolResultBinaryMiddleware,
    create_code_interpreter_middleware,
    create_retry_middleware,
)
from src.infra.backend import (
    LazySandboxBackend,
    create_persistent_backend,
    create_sandbox_backend,
)
from src.infra.goal import (
    build_goal_input,
    build_goal_prompt_section,
    create_goal_rubric_middleware,
)
from src.infra.llm.client import LLMClient
from src.infra.logging import get_logger
from src.infra.sandbox.session_manager import get_session_sandbox_manager
from src.infra.skill.loader import build_skills_prompt
from src.infra.storage.checkpoint import get_async_checkpointer
from src.infra.storage.mongodb_store import acreate_store
from src.infra.writer.present import Presenter
from src.kernel.config import settings

logger = get_logger(__name__)


# ============================================================================
# 节点函数
# ============================================================================


async def agent_node(state: Dict[str, Any], config: RunnableConfig) -> Dict[str, Any]:
    """
    Agent 主节点

    创建 deep agent (内层 graph) 并执行，通过 presenter 流式发送事件。
    历史消息从内层 graph 的 checkpoint 获取（MongoDB持久化）。
    """
    start_time = time.time()

    presenter = get_presenter(config)
    configurable = config.get("configurable", {})
    context: SearchAgentContext = configurable.get("context", SearchAgentContext())

    # 获取 agent_options
    agent_options = configurable.get("agent_options") or {}
    selected_model = agent_options.get("model")  # Per-request model override
    model_id = agent_options.get("model_id")  # Model config ID for specific channel/provider
    resolved_model_config = agent_options.get("_resolved_model_config")
    thinking_config = build_thinking_config(agent_options)
    logger.info(f"agent_options: {agent_options}")

    # 获取附件
    attachments = state.get("attachments", [])

    # 创建 LLM
    llm_start = time.time()
    llm = await LLMClient.get_model(
        model=selected_model,
        model_id=model_id,
        model_config=resolved_model_config,
        thinking=thinking_config,
    )
    llm_init_time = time.time() - llm_start
    logger.debug(f"[Agent] LLM init: {llm_init_time * 1000:.3f}ms")

    # 查询 fallback_model 配置
    fallback_model_value = agent_options.get("_resolved_fallback_model")
    if "_resolved_fallback_model" not in agent_options:
        fallback_model_value = await resolve_fallback_model(
            model_id, selected_model, log_prefix="[Agent]"
        )
    supports_vision = agent_options.get("_resolved_supports_vision")
    if supports_vision is None:
        supports_vision = await resolve_model_supports_vision(
            model_id, selected_model, log_prefix="[Agent]"
        )
    supports_vision = bool(supports_vision)
    image_url_to_base64 = agent_options.get("_resolved_image_url_to_base64")
    if image_url_to_base64 is None:
        image_url_to_base64 = await resolve_model_image_url_to_base64(
            model_id, selected_model, log_prefix="[Agent]"
        )
    image_url_to_base64 = bool(image_url_to_base64)

    # 多租户隔离
    tenant_id = context.user_id or "default"
    assistant_id = f"assistant-{tenant_id}"
    logger.info(f"tenant_id: {tenant_id}")

    # 创建 Backend 和获取系统提示
    backend_start = time.time()
    (
        backend,
        system_prompt,
        store,
        sandbox_backend,
        sandbox_work_dir,
    ) = await _create_backend_and_prompt(
        state=state,
        context=context,
        presenter=presenter,
        assistant_id=assistant_id,
    )
    backend_init_time = time.time() - backend_start
    logger.debug(f"[Agent] Backend init: {backend_init_time * 1000:.3f}ms")

    # 构建 persona + skills 提示（使用预加载的 skills，避免重复数据库查询）
    persona_sections = build_persona_prompt_sections(configurable.get("persona_system_prompt"))

    skills_prompt = ""
    if settings.ENABLE_SKILLS and context.skills:
        try:
            skills_prompt = await build_skills_prompt(context.skills)
        except Exception as e:
            logger.warning(f"Failed to build skills prompt: {e}")

    # 构建记忆系统提示
    memory_guide = get_memory_guide() if settings.ENABLE_MEMORY else ""

    # 过滤工具（懒加载 MCP 工具）
    get_tools = getattr(context, "get_tools", None)
    if callable(get_tools):
        maybe_tools = get_tools()
        if inspect.isawaitable(maybe_tools):
            await maybe_tools
    filter_tools = getattr(context, "filter_tools", None)
    filtered_tool_list = list(
        filter_tools() if callable(filter_tools) else getattr(context, "tools", [])
    )
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

    # 创建内层 graph (deep agent)
    checkpointer_start = time.time()
    inner_checkpointer = await get_async_checkpointer(thread_id=state.get("session_id"))
    checkpointer_init_time = time.time() - checkpointer_start
    logger.debug(f"[Agent] Checkpointer init: {checkpointer_init_time * 1000:.3f}ms")

    # 创建 graph（带计时）
    graph_compile_start = time.time()

    # 自定义子代理配置 - 强制将所有中间信息保存到文件
    search_base_url = configurable.get("base_url", "")
    subagent_prompt_sections = [s for s in (*persona_sections, skills_prompt, memory_guide) if s]
    if sandbox_backend and sandbox_work_dir:
        subagent_prompt_sections.append(SANDBOX_RUNTIME_SECTION.format(work_dir=sandbox_work_dir))

    def _build_subagent_middleware(subagent_type: str) -> list:
        mw = [
            create_todo_middleware(),
            *create_retry_middleware(fallback_model=fallback_model_value, thinking=thinking_config),
            ToolResultBinaryMiddleware(base_url=search_base_url),
            ArtifactDeliveryMiddleware(workspace_path=sandbox_work_dir),
            SubagentActivityMiddleware(backend=backend),
        ]
        if image_url_to_base64:
            mw.append(ImageUrlToBase64Middleware())
        if subagent_prompt_sections:
            mw.append(SectionPromptMiddleware(sections=subagent_prompt_sections))
        if sandbox_backend:
            mw.append(EnvVarPromptMiddleware(user_id=context.user_id or "default"))
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
        mw.append(PromptCachingMiddleware())
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

    # 构建中间件栈：retry → binary → skills+memory → sandbox runtime/tools → memory_index → tool search → cache tag
    # Order: stable → semi-stable → dynamic → cache breakpoint
    user_middleware = create_retry_middleware(
        fallback_model=fallback_model_value, thinking=thinking_config
    )
    user_middleware.append(ToolResultBinaryMiddleware(base_url=search_base_url))
    user_middleware.append(ArtifactDeliveryMiddleware(workspace_path=sandbox_work_dir))
    if image_url_to_base64:
        user_middleware.append(ImageUrlToBase64Middleware())
    # Prompt sections: one SectionPromptMiddleware instance, multiple ordered blocks.
    # Duplicate middleware classes are rejected by langchain's agent factory.
    _prompt_sections = [
        s
        for s in (*MAIN_AGENT_PROMPT_SECTIONS, *persona_sections, skills_prompt, memory_guide)
        if s
    ]
    active_goal = configurable.get("active_goal")
    goal_section = build_goal_prompt_section(active_goal)
    if goal_section:
        _prompt_sections.append(goal_section)
    if configurable.get("auto_mode"):
        _prompt_sections.append(AUTO_MODE_PROMPT_SECTION)
    if sandbox_backend and sandbox_work_dir:
        _prompt_sections.append(SANDBOX_RUNTIME_SECTION.format(work_dir=sandbox_work_dir))
    if _prompt_sections:
        user_middleware.append(SectionPromptMiddleware(sections=_prompt_sections))
    # Dynamic prompt order: env names → memory hints → deferred tools → sandbox inventory.
    if sandbox_backend:
        user_middleware.append(EnvVarPromptMiddleware(user_id=context.user_id or "default"))
    if settings.ENABLE_MEMORY and settings.NATIVE_MEMORY_INDEX_ENABLED and context.user_id:
        from src.infra.agent.middleware import MemoryIndexMiddleware

        user_middleware.append(MemoryIndexMiddleware(user_id=context.user_id))

    # Tool search: per-turn dynamic content
    if context.deferred_manager is not None:
        from src.infra.agent.middleware import ToolSearchMiddleware

        user_middleware.append(
            ToolSearchMiddleware(
                deferred_manager=context.deferred_manager,
                search_limit=settings.DEFERRED_TOOL_SEARCH_LIMIT,
            )
        )
        logger.info("[SearchAgent] Tool search middleware enabled (deferred MCP loading)")
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
    user_middleware.append(create_todo_middleware())

    # KV cache: tag final system block + last tool AFTER all dynamic injection
    user_middleware.append(PromptCachingMiddleware())

    inner_graph = create_deep_agent(
        model=llm,
        system_prompt=system_prompt,
        backend=backend,
        tools=filtered_tools,
        checkpointer=inner_checkpointer,
        store=store,  # 传递 PostgresStore
        skills=None,  # 禁用 SkillsMiddleware，使用 build_skills_prompt 代替
        subagents=custom_subagents,
        middleware=user_middleware,
    )
    graph_compile_time = time.time() - graph_compile_start
    logger.debug(f"[Agent] Graph compile: {graph_compile_time * 1000:.3f}ms")

    inner_config: RunnableConfig = {
        "configurable": build_nested_graph_configurable(
            thread_id=state.get("session_id", str(uuid.uuid4())),
            checkpointer=inner_checkpointer,
            backend=backend,
            context=context,  # 传递 context 以便工具访问 user_id
            disabled_skills=configurable.get("disabled_skills"),
            enabled_skills=configurable.get("enabled_skills"),
            base_url=configurable.get("base_url", ""),  # 传递 base_url 给工具使用
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
    user_input = state.get("input", "")
    recommendation_input = configurable.get("recommendation_input") or user_input
    if supports_vision:
        attachments = await inline_image_attachments_as_data_urls(
            attachments,
            base_url=configurable.get("base_url", ""),
            force_data_url=image_url_to_base64,
        )
    new_message = build_human_message(user_input, attachments, supports_vision=supports_vision)

    # 创建事件处理器（使用 AgentEventProcessor 处理 astream_events）
    logger.info("[SearchAgent] Creating AgentEventProcessor")
    event_processor = AgentEventProcessor(presenter, base_url=configurable.get("base_url", ""))

    logger.info("[SearchAgent] Starting astream_events")
    # 流式处理事件（不重试，直接调用）
    try:
        async with isolated_nested_graph_run():
            async for event in inner_graph.astream_events(  # type: ignore[call-overload]
                build_goal_input(new_message, active_goal, rubric_middleware=rubric_middleware),
                inner_config,
                version="v2",
            ):
                await event_processor.process_event(event)
    finally:
        await event_processor.flush()
        await emit_token_usage(
            event_processor,
            presenter,
            start_time,
            model_id=model_id,
            model=selected_model,
        )
    logger.info("[SearchAgent] astream_events completed")

    if settings.ENABLE_MEMORY and context.user_id:
        from src.infra.memory.tools import schedule_auto_memory_capture

        schedule_auto_memory_capture(context.user_id, user_input)

    # 持久化已发现的延迟工具名（跨 turn 恢复，分布式安全）
    session_id = state.get("session_id", "")
    if context.deferred_manager is not None and context.deferred_manager.discovered_count > 0:
        try:
            from src.infra.tool.deferred_manager import persist_discovered_tools

            await persist_discovered_tools(
                session_id,
                context.deferred_manager.discovered_names,
            )
        except Exception as e:
            logger.warning("持久化已发现工具失败 (search_agent): %s", e, exc_info=True)

    output_text = event_processor.output_text
    event_processor.clear()

    if recommendation_input and settings.ENABLE_RECOMMEND_QUESTIONS:
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

    return {"output": output_text}


async def _create_backend_and_prompt(
    state: Dict[str, Any],
    context: SearchAgentContext,
    presenter: Presenter,
    assistant_id: str,
) -> tuple[Any, str, Any, Any, str | None]:
    """
    创建 Backend 实例和系统提示

    根据是否启用沙箱模式，返回相应的 Backend 实例和系统提示。
    skills 和 memory_guide 的注入由 SectionPromptMiddleware 在请求时完成（KV cache 友好）。

    Args:
        state: 状态字典
        context: Agent 上下文
        presenter: 输出处理器
        assistant_id: 助手 ID

    Returns:
        (backend, system_prompt, store, sandbox_backend, sandbox_work_dir) 元组。
        sandbox_backend 在沙箱模式下为 LazySandboxBackend 实例，否则为 None。
    """
    # 创建 store（优先 PostgreSQL → MongoDB fallback）
    store = await acreate_store()

    # 获取 user_id
    user_id = context.user_id or "default"

    if not settings.ENABLE_SANDBOX:
        # 非沙箱模式：使用持久化 backend（PostgreSQL 或 MongoDB，由 store 决定）
        logger.info(f"Sandbox disabled, using PersistentBackend for assistant: {assistant_id}")
        backend = create_persistent_backend(
            assistant_id,
            user_id=user_id,
            session_id=state.get("session_id", str(uuid.uuid4())),
        )
        prompt = DEFAULT_SYSTEM_PROMPT
        return backend, prompt, store, None, None

    # 沙箱模式
    if not context.user_id:
        raise ValueError("Sandbox requires authenticated user (user_id is required)")

    session_id = state.get("session_id") or context.session_id
    sandbox_backend = LazySandboxBackend(
        session_id=session_id,
        user_id=context.user_id,
        presenter=presenter,
        manager_factory=get_session_sandbox_manager,
    )
    context.set_run_sandbox(sandbox_backend)
    logger.info(f"Sandbox enabled, using lazy sandbox backend for assistant: {assistant_id}")

    return (
        create_sandbox_backend(sandbox_backend, assistant_id, user_id=user_id),
        SANDBOX_SYSTEM_PROMPT,
        store,
        sandbox_backend,
        sandbox_backend.work_dir,
    )
