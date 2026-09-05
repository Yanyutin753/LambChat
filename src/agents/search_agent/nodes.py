"""
Search Agent 节点

LangGraph 节点函数，使用 deep agent 执行任务。
后续可扩展：retrieve_node, summarize_node 等。
"""

import inspect
import time
import uuid
from typing import Any, Dict, cast

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
    build_response_language_section,
    get_memory_guide,
)
from src.agents.core.thinking import build_thinking_config
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
    MemoryRecallIndexMiddleware,
    SectionPromptMiddleware,
    SteerMiddleware,
    SubagentActivityMiddleware,
    SubagentResultHandoffMiddleware,
    ToolResultBinaryMiddleware,
    create_code_interpreter_middleware,
    create_retry_middleware,
    summarization_fallback_patch,
)
from src.infra.backend import (
    LazySandboxBackend,
    create_persistent_backend,
    create_sandbox_backend,
)
from src.infra.envvar.sync import sync_sandbox_env_vars
from src.infra.goal import (
    build_goal_input,
    create_goal_rubric_middleware,
)
from src.infra.llm.client import LLMClient
from src.infra.logging import get_logger
from src.infra.sandbox.session_manager import get_session_sandbox_manager
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

    # 多租户隔离
    tenant_id = context.user_id or "default"
    assistant_id = f"assistant-{tenant_id}"
    logger.info(f"tenant_id: {tenant_id}")

    # 构建 persona + skills 提示（使用预加载的 skills，避免重复数据库查询）
    persona_sections = build_persona_prompt_sections(configurable.get("persona_system_prompt"))

    # 构建记忆系统提示
    memory_guide = get_memory_guide() if settings.ENABLE_MEMORY else ""

    async def _load_model_bundle() -> tuple[Any, Any, bool, bool]:
        llm_start = time.time()
        model = await LLMClient.get_model(
            model=selected_model,
            model_id=model_id,
            model_config=resolved_model_config,
            thinking=thinking_config,
        )
        logger.debug(f"[Agent] LLM init: {(time.time() - llm_start) * 1000:.3f}ms")

        fallback = agent_options.get("_resolved_fallback_model")
        if "_resolved_fallback_model" not in agent_options:
            fallback = await resolve_fallback_model(model_id, selected_model, log_prefix="[Agent]")
        vision = agent_options.get("_resolved_supports_vision")
        if vision is None:
            vision = await resolve_model_supports_vision(
                model_id, selected_model, log_prefix="[Agent]"
            )
        convert_images = agent_options.get("_resolved_image_url_to_base64")
        if convert_images is None:
            convert_images = await resolve_model_image_url_to_base64(
                model_id, selected_model, log_prefix="[Agent]"
            )
        return model, fallback, bool(vision), bool(convert_images)

    async def _load_backend_bundle() -> tuple[Any, str, Any, Any, str | None]:
        backend_start = time.time()
        result = await _create_backend_and_prompt(
            state=state,
            context=context,
            presenter=presenter,
            assistant_id=assistant_id,
            agent_options=agent_options,
        )
        logger.debug(f"[Agent] Backend init: {(time.time() - backend_start) * 1000:.3f}ms")
        return result

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
    backend, system_prompt, store, sandbox_backend, sandbox_work_dir = prepared.backend
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

    # 创建 graph（带计时）
    graph_compile_start = time.time()

    # 自定义子代理配置 - 强制将所有中间信息保存到文件
    search_base_url = configurable.get("base_url", "")
    subagent_prompt_sections = [s for s in (*persona_sections, memory_guide) if s]
    sandbox_runtime_policy = (
        SANDBOX_RUNTIME_SECTION.format(work_dir=sandbox_work_dir)
        if sandbox_backend and sandbox_work_dir
        else ""
    )

    def _build_subagent_middleware(subagent_type: str) -> list:
        mw = [
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
        if sandbox_runtime_policy:
            from src.infra.agent.middleware import SandboxWorkspaceMiddleware

            mw.append(SandboxWorkspaceMiddleware(policy_text=sandbox_runtime_policy))
        if context.deferred_manager is not None:
            from src.infra.agent.middleware import ToolSearchMiddleware

            subagent_deferred_manager = context.deferred_manager.fork_for_scope(
                f"subagent:{subagent_type}"
            )
            mw.append(
                ToolSearchMiddleware(
                    deferred_manager=subagent_deferred_manager,
                    search_limit=settings.DEFERRED_TOOL_SEARCH_LIMIT,
                    user_id=context.user_id,
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

    # 构建中间件栈：steer → retry → binary → authored prompts → sandbox tools → memory_index → tool search
    user_middleware = create_retry_middleware(
        fallback_model=fallback_model_value, thinking=thinking_config
    )
    user_middleware.insert(
        0, SteerMiddleware(session_id=str(state.get("session_id") or ""), presenter=presenter)
    )
    user_middleware.append(ToolResultBinaryMiddleware(base_url=search_base_url))
    user_middleware.append(ArtifactDeliveryMiddleware(workspace_path=sandbox_work_dir))
    if image_url_to_base64:
        user_middleware.append(ImageUrlToBase64Middleware())
    active_goal = configurable.get("active_goal")
    # Prompt sections use one SectionPromptMiddleware instance.
    # Duplicate middleware classes are rejected by langchain's agent factory.
    _prompt_sections = [
        s
        for s in (
            *MAIN_AGENT_PROMPT_SECTIONS,
            *persona_sections,
            memory_guide,
            build_response_language_section(agent_options.get("response_language")),
        )
        if s
    ]
    if _prompt_sections:
        user_middleware.append(SectionPromptMiddleware(sections=_prompt_sections))
    if settings.ENABLE_MEMORY and context.user_id:
        user_middleware.append(
            MemoryRecallIndexMiddleware(
                user_id=context.user_id,
                session_id=str(state.get("session_id") or "") or None,
            )
        )
    if sandbox_backend:
        user_middleware.append(EnvVarPromptMiddleware(user_id=context.user_id or "default"))
        # 沙箱统一确认门（本地 + 云端）：整批单次 interrupt，本地读 daemon
        # 上报策略，云端读用户 metadata 偏好（未设置归 none 保持云上历史行为）
        from src.infra.agent.middleware.sandbox_confirm import (
            SandboxConfirmMiddleware,
            _CloudPolicyResolver,
        )
        from src.infra.backend.local import WorkspaceAliasBackend

        user_middleware.append(
            SandboxConfirmMiddleware(
                user_id=context.user_id or "default",
                policy_resolver=(
                    None
                    if isinstance(sandbox_backend, WorkspaceAliasBackend)
                    else _CloudPolicyResolver(context.user_id or "default")
                ),
            )
        )
        if sandbox_work_dir:
            from src.infra.agent.middleware import SandboxWorkspaceMiddleware

            user_middleware.append(
                SandboxWorkspaceMiddleware(
                    policy_text=SANDBOX_RUNTIME_SECTION.format(work_dir=sandbox_work_dir)
                )
            )
    # Tool search: per-turn dynamic content
    if context.deferred_manager is not None:
        from src.infra.agent.middleware import ToolSearchMiddleware

        user_middleware.append(
            ToolSearchMiddleware(
                deferred_manager=context.deferred_manager,
                search_limit=settings.DEFERRED_TOOL_SEARCH_LIMIT,
                user_id=context.user_id,
            )
        )
        logger.info("[SearchAgent] Tool search middleware enabled (deferred MCP loading)")
    user_middleware.extend(
        create_code_interpreter_middleware(
            agent_options, sandbox_active=sandbox_backend is not None
        )
    )
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
    # HITL 恢复运行（issue #218）：以 Command(resume=...) 从挂起断点继续，
    # 不注入新的用户消息。
    hitl_resume = configurable.get("hitl_resume")
    if hitl_resume is not None:
        from langgraph.types import Command

        resume_map = hitl_resume.get("resume_value")
        sandbox_message = hitl_resume.get("sandbox_confirm_message")
        if sandbox_message and isinstance(resume_map, dict):
            # 沙箱确认门整批：同批全部中断共享批复值（并行工具各任务各中断）
            from src.infra.task.hitl import expand_sandbox_confirm_resume

            resume_map = await expand_sandbox_confirm_resume(
                inner_graph, inner_config, resume_map, message=sandbox_message
            )
        graph_input: Any = Command(resume=resume_map)
    else:
        if supports_vision:
            attachments = await inline_image_attachments_as_data_urls(
                attachments,
                base_url=configurable.get("base_url", ""),
                force_data_url=image_url_to_base64,
            )
        new_message = build_human_message(user_input, attachments, supports_vision=supports_vision)
        graph_input = build_goal_input(
            new_message, active_goal, rubric_middleware=rubric_middleware
        )

    # 创建事件处理器（使用 AgentEventProcessor 处理 astream_events）
    logger.info("[SearchAgent] Creating AgentEventProcessor")
    event_processor = AgentEventProcessor(
        presenter,
        base_url=configurable.get("base_url", ""),
        before_tool_start=(
            sandbox_backend.before_tool_start if sandbox_backend is not None else None
        ),
    )

    logger.info("[SearchAgent] Starting astream_events")
    # 流式处理事件（不重试，直接调用）
    # interrupt 模式在任意 checkpointer（包括进程内 MemorySaver）可用。
    from src.infra.tool.human_tool.runtime import (
        hitl_interrupt_supported,
        interrupt_supported_for_checkpointer,
    )

    interrupt_supported = interrupt_supported_for_checkpointer(inner_checkpointer)
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
    logger.info("[SearchAgent] astream_events completed")

    # 检测 interrupt 挂起（issue #218）：图存在待恢复任务时标记 WAITING_HUMAN，
    # 并将 ask_human interrupt payload 物化为审批记录 + SSE 通知
    # （工具内零副作用，对齐 deepagents 官方 HITL，重放不会重复创建）
    if interrupt_supported:
        try:
            snapshot = await inner_graph.aget_state(inner_config)  # type: ignore[attr-defined]
            if isinstance(inner_config, dict):
                cast(dict[str, Any], inner_config)["_recommendation_state_snapshot"] = snapshot
            if snapshot is not None and snapshot.next:
                presenter.hitl_suspended = True
                logger.info(
                    "[SearchAgent] Graph suspended by interrupt: session=%s run_id=%s",
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
                    trace_id=getattr(presenter, "trace_id", None) or ctx.trace_id,
                    user_id=context.user_id or ctx.user_id,
                    resume_context={
                        "active_goal": active_goal,
                        "recommendation_input": recommendation_input,
                        "goal_started_at": configurable.get("goal_started_at"),
                    },
                )
        except Exception as e:
            logger.warning("[SearchAgent] Failed to inspect graph state after run: %s", e)

    if settings.ENABLE_MEMORY and context.user_id:
        # Codex 式 Phase 1 记忆提取：run 结束后 kick 一轮「空闲会话」扫描，
        # 完整会话转录提炼 raw_memory（替代旧的每轮最后一条交换评估器）。
        from src.infra.memory.extraction import schedule_memory_extraction

        schedule_memory_extraction(context.user_id)

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

    if (
        recommendation_input
        and settings.ENABLE_RECOMMEND_QUESTIONS
        and not getattr(presenter, "hitl_suspended", False)
    ):
        from src.agents.core.recommendations import schedule_recommendations_best_effort

        schedule_recommendations_best_effort(
            presenter, recommendation_input, output_text, inner_graph, inner_config, agent_options
        )

    return {"output": output_text}


def _resolve_sandbox_platform(agent_options: Dict[str, Any] | None, default_platform: str) -> str:
    """会话级沙箱选择：agent_options.sandbox 覆盖全局平台（spec §3.4）。"""
    choice = (agent_options or {}).get("sandbox")
    # 非字符串值（如列表/字典，不可哈希）不能进 set 成员判断，回退默认平台
    return choice if isinstance(choice, str) and choice in {"local", "cloud"} else default_platform


async def _create_backend_and_prompt(
    state: Dict[str, Any],
    context: SearchAgentContext,
    presenter: Presenter,
    assistant_id: str,
    agent_options: Dict[str, Any] | None = None,
) -> tuple[Any, str, Any, Any, str | None]:
    """
    创建 Backend 实例和系统提示

    根据是否启用沙箱模式，返回相应的 Backend 实例和系统提示。
    skills 和 memory_guide 由 SectionPromptMiddleware 在模型请求时分段注入。

    Args:
        state: 状态字典
        context: Agent 上下文
        presenter: 输出处理器
        assistant_id: 助手 ID
        agent_options: 会话级选项；sandbox=local 时路由到本地沙箱后端

    Returns:
        (backend, system_prompt, store, sandbox_backend, sandbox_work_dir) 元组。
        sandbox_backend 在沙箱模式下为 LazySandboxBackend（云端）或
        WorkspaceAliasBackend（agent_options.sandbox=local，别名剥离器）实例，
        否则为 None。
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
    platform = _resolve_sandbox_platform(agent_options, settings.SANDBOX_PLATFORM.lower())
    if platform == "local":
        from src.infra.backend.local import WorkspaceAliasBackend

        # WorkspaceAliasBackend：prompt_policy 让模型用 /workspace/{sid}/x 别名
        # 路径调文件工具，别名剥离层把路径翻译回相对路径再构造命令（F1）。
        local_backend = WorkspaceAliasBackend(user_id=user_id, session_id=session_id)
        # 用户 env 变量注入（对齐云端：backend.env_vars → 执行时下发）；
        # env_var 工具运行中改动经 sync_envvar_change 实时刷新同一属性
        await sync_sandbox_env_vars(local_backend, user_id)
        logger.info(
            f"Sandbox enabled (local), using local sandbox backend for assistant: {assistant_id}"
        )
        # 本地 daemon 常驻用户机器：无云端沙箱需要懒初始化/释放，
        # 因此不走 LazySandboxBackend，也不注册 context.run_sandbox。
        return (
            create_sandbox_backend(local_backend, assistant_id, user_id=user_id),
            SANDBOX_SYSTEM_PROMPT,
            store,
            local_backend,
            local_backend.work_dir,
        )
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
