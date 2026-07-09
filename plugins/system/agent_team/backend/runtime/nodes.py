"""
Team Agent 节点 - 团队路由，角色分派

基于 fast_agent/nodes.py 扩展，增加团队解析和多角色子代理。
"""

import time
import uuid
from typing import Any, Dict

from deepagents import create_deep_agent
from deepagents.middleware.subagents import CompiledSubAgent, SubAgent
from langchain_core.runnables import RunnableConfig

from plugins.system.agent_team.backend.runtime.context import TeamAgentContext
from plugins.system.agent_team.backend.runtime.prompt import (
    build_team_member_subagent_type,
    build_team_router_system_prompt,
    build_team_subagent_avatars,
    build_team_subagent_display_names,
    summarize_role_system_prompt,
)
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
    build_role_subagent_section,
    get_memory_guide,
)
from src.agents.core.thinking import build_thinking_config
from src.agents.fast_agent.prompt import FAST_SYSTEM_PROMPT
from src.agents.search_agent.prompt import (
    SANDBOX_RUNTIME_SECTION as SEARCH_SANDBOX_RUNTIME_SECTION,
)
from src.agents.search_agent.prompt import (
    SANDBOX_SYSTEM_PROMPT as SEARCH_SANDBOX_SYSTEM_PROMPT,
)
from src.infra.agent import AgentEventProcessor
from src.infra.agent.events.types import TOOL_TASK
from src.infra.agent.middleware import (
    ArtifactDeliveryMiddleware,
    EnvVarPromptMiddleware,
    ImageUrlToBase64Middleware,
    MainAgentContextMiddleware,
    PromptCachingMiddleware,
    SandboxMCPMiddleware,
    SectionPromptMiddleware,
    SubagentActivityMiddleware,
    SubagentExecutionPolicyMiddleware,
    SubagentResultHandoffMiddleware,
    TaskDelegationEnvelopeMiddleware,
    TeamRouterDelegationGuardMiddleware,
    ToolResultBinaryMiddleware,
    create_code_interpreter_middleware,
    create_retry_middleware,
)
from src.infra.backend import (
    create_persistent_backend_factory,
    create_sandbox_backend_factory,
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
from src.kernel.config import settings
from src.kernel.schemas.model import ModelConfig

logger = get_logger(__name__)

_FULL_ASSET_PACKAGE_DIRECT_TRIGGERS = (
    "完整素材包",
    "全套素材包",
)
_FULL_ASSET_PACKAGE_STAGE_TRIGGERS = (
    "分镜",
    "提示词",
    "首帧",
    "交付",
    "四阶段",
    "素材包流程",
)

# ============================================================================
# 节点函数
# ============================================================================


def build_no_team_fallback_system_prompt(*, sandbox_active: bool) -> str:
    """Choose the single-agent fallback prompt when no explicit team is selected."""
    if sandbox_active:
        return SEARCH_SANDBOX_SYSTEM_PROMPT
    return FAST_SYSTEM_PROMPT


def _is_full_asset_package_request(user_input: Any) -> bool:
    text = str(user_input or "").casefold()
    if any(trigger in text for trigger in _FULL_ASSET_PACKAGE_DIRECT_TRIGGERS):
        return True
    return "素材包" in text and any(
        trigger in text for trigger in _FULL_ASSET_PACKAGE_STAGE_TRIGGERS
    )


def _collect_event_tool_names(event: Any) -> set[str]:
    if not isinstance(event, dict):
        return set()

    names: set[str] = set()

    def add_name(value: Any) -> None:
        if isinstance(value, str) and value.strip():
            names.add(value.strip())

    def collect_from_mapping(value: Any) -> None:
        if not isinstance(value, dict):
            return
        for key in ("name", "tool", "tool_name", "subagent_type"):
            add_name(value.get(key))
        tool_call = value.get("tool_call")
        if isinstance(tool_call, dict):
            collect_from_mapping(tool_call)
        tool_calls = value.get("tool_calls")
        if isinstance(tool_calls, list):
            for item in tool_calls:
                collect_from_mapping(item)

    collect_from_mapping(event)
    data = event.get("data")
    collect_from_mapping(data)
    if isinstance(data, dict):
        collect_from_mapping(data.get("input"))
        collect_from_mapping(data.get("output"))
        chunk = data.get("chunk")
        collect_from_mapping(chunk)
        tool_calls = getattr(chunk, "tool_calls", None)
        if isinstance(tool_calls, list):
            for item in tool_calls:
                collect_from_mapping(item)

    return names


def _is_team_delegation_event(event: Any, subagent_names: set[str]) -> bool:
    if not isinstance(event, dict):
        return False
    if event.get("event") not in {"on_tool_start", "on_tool_end", "on_tool_error"}:
        return False
    tool_names = _collect_event_tool_names(event)
    return TOOL_TASK in tool_names or bool(tool_names & subagent_names)


def _raise_if_team_router_completed_without_required_delegation(
    *,
    team: Any,
    user_input: Any,
    delegation_event_count: int,
) -> None:
    if not team or not getattr(team, "active_members", None):
        return
    if delegation_event_count > 0:
        return
    if not _is_full_asset_package_request(user_input):
        return

    logger.warning(
        "[TeamAgent] Blocking router completion without delegation for full asset-package "
        "request: team_id=%s team_name=%s",
        getattr(team, "id", None),
        getattr(team, "name", None),
    )
    raise ValueError("team_router_delegation_required:full_asset_package")


async def resolve_runtime_team(
    *,
    team_id: str | None,
    context: TeamAgentContext,
    user_input: str,
):
    """Resolve an explicit team; no team means single-agent fallback."""
    del user_input
    if not context.user_id:
        return None

    if team_id:
        try:
            from plugins.system.agent_team.backend.domain.manager import get_team_manager

            tm = get_team_manager()
            team = await tm.resolve_team_for_runtime(team_id, owner_user_id=context.user_id)
            if team:
                logger.info(
                    f"[TeamAgent] Resolved team '{team.name}' "
                    f"with {len(team.active_members)} active members"
                )
                return team
            logger.info("[TeamAgent] Team resolved to None (no active members or not found)")
            raise ValueError("team_not_found_or_unavailable")
        except Exception as e:
            if isinstance(e, ValueError) and str(e) == "team_not_found_or_unavailable":
                raise
            logger.warning(f"[TeamAgent] Failed to resolve team: {e}")
            raise ValueError("team_not_found_or_unavailable") from e

    return None


async def resolve_team_member_model_config(
    member_model_id: str | None,
    *,
    user_id: str | None = None,
) -> ModelConfig | None:
    """Resolve and validate a team member model override for runtime use."""
    if not member_model_id:
        return None

    from src.infra.agent.model_storage import get_model_storage

    try:
        model = await get_model_storage().get(member_model_id)
    except Exception as e:
        logger.warning("[TeamAgent] Failed to resolve member model %s: %s", member_model_id, e)
        raise ValueError("team_member_model_unavailable") from e

    if not model or not model.enabled:
        raise ValueError("team_member_model_unavailable")

    if user_id:
        try:
            from src.infra.agent.model_access import resolve_user_allowed_model_ids
            from src.infra.user.storage import UserStorage
            from src.kernel.schemas.user import TokenPayload

            user = await UserStorage().get_by_id(user_id)
            if not user:
                raise ValueError("team_member_model_not_allowed")
            allowed_model_ids = await resolve_user_allowed_model_ids(
                TokenPayload(
                    sub=user.id,
                    username=user.username,
                    roles=user.roles,
                    permissions=user.permissions,
                )
            )
            if allowed_model_ids is not None:
                allowed = set(allowed_model_ids)
                if model.id not in allowed and model.value not in allowed:
                    raise ValueError("team_member_model_not_allowed")
        except ValueError:
            raise
        except Exception as e:
            logger.warning(
                "[TeamAgent] Failed to validate member model access %s: %s",
                member_model_id,
                e,
            )
            raise ValueError("team_member_model_unavailable") from e
    return model


def _safe_member_model_config_dict(model: ModelConfig) -> dict[str, Any]:
    return model.model_copy(update={"api_key": None}).model_dump(mode="json")


async def team_router_node(state: Dict[str, Any], config: RunnableConfig) -> Dict[str, Any]:
    """
    Team Router 主节点 - 团队路由，角色分派

    特点：
    - 解析团队配置，按角色构建子代理
    - 使用 SectionPromptMiddleware 为每个角色注入角色、技能、记忆和运行时提示
    - 无团队时回退到单代理模式
    """
    start_time = time.time()

    presenter = get_presenter(config)
    configurable = config.get("configurable", {})
    context: TeamAgentContext = configurable.get("context", TeamAgentContext())

    # 获取 agent_options
    agent_options = configurable.get("agent_options") or {}
    selected_model = agent_options.get("model")
    model_id = agent_options.get("model_id")
    resolved_model_config = agent_options.get("_resolved_model_config")
    thinking_config = build_thinking_config(agent_options)

    # 获取附件
    attachments = state.get("attachments", [])

    # 创建 LLM
    llm_start = time.time()
    llm = await LLMClient.get_model(
        model=selected_model,
        model_id=model_id,
        model_config=resolved_model_config,
        thinking=thinking_config,
        streaming=False,
    )
    llm_init_time = time.time() - llm_start
    logger.debug(f"[TeamAgent] LLM init: {llm_init_time * 1000:.3f}ms")

    # 查询 fallback_model 配置
    fallback_model_value = agent_options.get("_resolved_fallback_model")
    if "_resolved_fallback_model" not in agent_options:
        fallback_model_value = await resolve_fallback_model(
            model_id, selected_model, log_prefix="[TeamAgent]"
        )
    supports_vision = agent_options.get("_resolved_supports_vision")
    if supports_vision is None:
        supports_vision = await resolve_model_supports_vision(
            model_id, selected_model, log_prefix="[TeamAgent]"
        )
    supports_vision = bool(supports_vision)
    image_url_to_base64 = agent_options.get("_resolved_image_url_to_base64")
    if image_url_to_base64 is None:
        image_url_to_base64 = await resolve_model_image_url_to_base64(
            model_id, selected_model, log_prefix="[TeamAgent]"
        )
    image_url_to_base64 = bool(image_url_to_base64)

    # 多租户隔离
    tenant_id = context.user_id or "default"
    assistant_id = f"assistant-{tenant_id}"
    session_id = state.get("session_id", str(uuid.uuid4()))

    # ── 团队解析 ──
    user_input = state.get("input", "")
    team = await resolve_runtime_team(
        team_id=configurable.get("team_id"),
        context=context,
        user_input=user_input,
    )
    sandbox_requested = bool(team.run_in_sandbox) if team else bool(settings.ENABLE_SANDBOX)
    sandbox_active = bool(settings.ENABLE_SANDBOX and sandbox_requested)

    # ── 系统提示 ──
    # In explicit team mode the main agent is only the router/synthesizer.
    # Role persona and skills are injected into the matching member subagents.
    persona_sections = (
        [] if team else build_persona_prompt_sections(configurable.get("persona_system_prompt"))
    )

    skills_prompt = ""
    if settings.ENABLE_SKILLS and context.skills:
        try:
            skills_start = time.time()
            skills_prompt = await build_skills_prompt(context.skills)
            skills_init_time = time.time() - skills_start
            logger.debug(f"[TeamAgent] Skills prompt init: {skills_init_time * 1000:.3f}ms")
        except Exception as e:
            logger.warning(f"Failed to build skills prompt: {e}")
    router_skills_prompt = "" if team else skills_prompt

    memory_guide = get_memory_guide() if settings.ENABLE_MEMORY else ""
    role_system_prompts: dict[str, str] = {}
    role_skill_prompts: dict[str, str] = {}
    role_summaries: dict[str, str] = {}

    if team and team.active_members:
        try:
            from src.infra.persona_preset.manager import get_persona_preset_manager

            preset_mgr = get_persona_preset_manager()
            for member in team.active_members:
                preset_snapshot = await preset_mgr.use_preset(
                    member.persona_preset_id,
                    user_id=context.user_id or "default",
                    is_admin=False,
                )
                role_system_prompts[member.member_id] = preset_snapshot.system_prompt
                role_skill_names = set(getattr(preset_snapshot, "skill_names", []) or [])
                if role_skill_names:
                    role_skills = [
                        skill for skill in context.skills if skill.get("name") in role_skill_names
                    ]
                    role_skill_prompts[member.member_id] = await build_skills_prompt(role_skills)
                else:
                    role_skill_prompts[member.member_id] = skills_prompt
                summary = summarize_role_system_prompt(preset_snapshot.system_prompt)
                if summary:
                    role_summaries[member.member_id] = summary
        except Exception as e:
            logger.warning(f"[TeamAgent] Failed to resolve team member preset prompts: {e}")
            raise ValueError("team_member_preset_unavailable") from e

    if team:
        default_role = "general-purpose"
        if team.default_member_id:
            default_member = next(
                (m for m in team.active_members if m.member_id == team.default_member_id),
                team.active_members[0] if team.active_members else None,
            )
            default_role = (
                build_team_member_subagent_type(default_member)
                if default_member
                else "general-purpose"
            )
        else:
            default_role = (
                build_team_member_subagent_type(team.active_members[0])
                if team.active_members
                else "general-purpose"
            )
        system_prompt = build_team_router_system_prompt(
            team,
            default_role=default_role,
            role_summaries=role_summaries,
        )
    else:
        system_prompt = FAST_SYSTEM_PROMPT
    runtime_enabled_skills = None if team else configurable.get("enabled_skills")

    # 创建 backend
    backend_start = time.time()
    sandbox_backend = None
    sandbox_work_dir = None

    if not sandbox_active:
        backend_factory = create_persistent_backend_factory(
            assistant_id=assistant_id,
            user_id=context.user_id,
            session_id=session_id,
        )
        logger.info(
            "[TeamAgent] Sandbox inactive, using PersistentBackend for assistant: %s "
            "team_id=%s team_requested_sandbox=%s global_sandbox_enabled=%s",
            assistant_id,
            getattr(team, "id", None),
            sandbox_requested,
            settings.ENABLE_SANDBOX,
        )
    else:
        if not context.user_id:
            raise ValueError("Sandbox requires authenticated user (user_id is required)")

        sandbox_manager = get_session_sandbox_manager()
        try:
            await presenter.emit_sandbox_starting()
        except Exception as e:
            logger.warning(f"Failed to emit sandbox:starting event: {e}")

        try:
            sandbox_backend, sandbox_work_dir = await sandbox_manager.get_or_create(
                session_id=state.get("session_id", str(uuid.uuid4())),
                user_id=context.user_id,
            )
            try:
                sandbox_id = getattr(sandbox_backend.default, "id", "unknown")
                await presenter.emit_sandbox_ready(
                    sandbox_id=sandbox_id,
                    work_dir=sandbox_work_dir,
                )
            except Exception as e:
                logger.warning(f"Failed to emit sandbox:ready event: {e}")

            backend_factory = create_sandbox_backend_factory(
                sandbox_backend.default,
                assistant_id,
                user_id=context.user_id,
            )
            if team:
                system_prompt = f"{SEARCH_SANDBOX_SYSTEM_PROMPT}\n\n{system_prompt}"
            else:
                system_prompt = build_no_team_fallback_system_prompt(sandbox_active=True)
            logger.info(
                f"[TeamAgent] Sandbox enabled, using sandbox backend for assistant: {assistant_id}"
            )
        except Exception as e:
            try:
                await presenter.emit_sandbox_error(f"沙箱初始化失败: {str(e)}")
            except Exception as emit_err:
                logger.warning(f"Failed to emit sandbox:error event: {emit_err}")
            raise

    backend = backend_factory(None) if callable(backend_factory) else backend_factory
    backend_init_time = time.time() - backend_start
    logger.debug(f"[TeamAgent] Backend init: {backend_init_time * 1000:.3f}ms")

    # 创建 store
    store = await acreate_store()

    # 过滤工具（懒加载 MCP 工具）
    filtered_tools = None
    if hasattr(context, "get_tools") and hasattr(context, "filter_tools"):
        await context.get_tools()
        filtered_tools = context.filter_tools() or None

        if context.deferred_manager is not None and filtered_tools is not None:
            from src.infra.tool.tool_search_tool import ToolSearchTool

            search_tool = ToolSearchTool(
                manager=context.deferred_manager,
                search_limit=settings.DEFERRED_TOOL_SEARCH_LIMIT,
            )
            filtered_tools.append(search_tool)

    # 创建内层 graph (deep agent)
    checkpointer_start = time.time()
    inner_checkpointer = await get_async_checkpointer(thread_id=state.get("session_id"))
    checkpointer_init_time = time.time() - checkpointer_start
    logger.debug(f"[TeamAgent] Checkpointer init: {checkpointer_init_time * 1000:.3f}ms")

    graph_compile_start = time.time()

    # ── 子代理配置 ──
    subagent_base_url = configurable.get("base_url", "")

    def _build_subagent_middleware(
        subagent_type: str = "general-purpose",
        prompt_sections: list[str] | None = None,
        fallback_model: str | None = fallback_model_value,
        should_convert_image_url_to_base64: bool = image_url_to_base64,
    ) -> list:
        """Build the middleware stack for a single subagent."""
        mw = [
            *create_retry_middleware(fallback_model=fallback_model, thinking=thinking_config),
            ToolResultBinaryMiddleware(base_url=subagent_base_url),
            ArtifactDeliveryMiddleware(workspace_path=sandbox_work_dir),
            SubagentActivityMiddleware(backend=backend),
        ]
        if team:
            mw.append(SubagentExecutionPolicyMiddleware())
        if should_convert_image_url_to_base64:
            mw.append(ImageUrlToBase64Middleware())
        if prompt_sections:
            mw.append(SectionPromptMiddleware(sections=prompt_sections))
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

    custom_subagents: list[SubAgent | CompiledSubAgent] = []
    subagent_display_names: dict[str, str] = {}
    subagent_avatars: dict[str, str] = {}
    subagent_runtime_section = (
        SEARCH_SANDBOX_RUNTIME_SECTION.format(work_dir=sandbox_work_dir)
        if sandbox_backend and sandbox_work_dir
        else None
    )

    if team and team.active_members:
        # ── 多角色子代理 ──
        try:
            subagent_display_names = build_team_subagent_display_names(team)
            subagent_avatars = build_team_subagent_avatars(team)

            for member in team.active_members:
                subagent_type = build_team_member_subagent_type(member)
                role_name = member.role_name or subagent_type
                member_model_config = await resolve_team_member_model_config(
                    member.model_id,
                    user_id=context.user_id,
                )
                member_model = None
                member_fallback_model = fallback_model_value
                member_image_url_to_base64 = image_url_to_base64
                if member_model_config is not None:
                    member_model = await LLMClient.get_model(
                        model=member_model_config.value,
                        model_id=member_model_config.id,
                        model_config=_safe_member_model_config_dict(member_model_config),
                        thinking=thinking_config,
                        streaming=False,
                    )
                    member_fallback_model = await resolve_fallback_model(
                        member_model_config.id,
                        member_model_config.value,
                        log_prefix=f"[TeamAgent:{subagent_type}]",
                    )
                    member_image_url_to_base64 = bool(
                        getattr(member_model_config.profile, "image_url_to_base64", False)
                        if member_model_config.profile
                        else False
                    )
                    logger.info(
                        "[TeamAgent] Role subagent model override: type=%s role=%s model_id=%s model=%s",
                        subagent_type,
                        role_name,
                        member_model_config.id,
                        member_model_config.value,
                    )
                role_section = build_role_subagent_section(
                    role_name=role_name,
                    role_system_prompt=role_system_prompts[member.member_id],
                    team_name=team.name,
                    team_instructions=team.team_instructions or None,
                    role_instructions=member.role_instructions or None,
                )
                role_prompt_sections = [
                    s
                    for s in (
                        role_section,
                        role_skill_prompts.get(member.member_id, skills_prompt),
                        memory_guide,
                        subagent_runtime_section,
                    )
                    if s
                ]
                logger.info(
                    "[TeamAgent] Role subagent prompt built: type=%s role=%s "
                    "section_chars=%d has_role_prompt=%s has_role_instructions=%s "
                    "has_skills=%s",
                    subagent_type,
                    role_name,
                    sum(len(s) for s in role_prompt_sections),
                    bool(role_system_prompts[member.member_id].strip())
                    and role_system_prompts[member.member_id].strip() in role_section,
                    bool((member.role_instructions or "").strip())
                    and (member.role_instructions or "").strip() in role_section,
                    any("## Skills System" in s for s in role_prompt_sections),
                )
                subagent_config: SubAgent = {
                    "name": subagent_type,
                    "description": (
                        f"Team member '{role_name}' "
                        f"(member_id: {member.member_id}). "
                        f"Dispatch tasks matching this role's expertise."
                        + (f" {member.role_instructions}" if member.role_instructions else "")
                    ),
                    "system_prompt": SUBAGENT_PROMPT,
                    "middleware": _build_subagent_middleware(
                        subagent_type,
                        prompt_sections=role_prompt_sections,
                        fallback_model=member_fallback_model,
                        should_convert_image_url_to_base64=member_image_url_to_base64,
                    ),
                }
                if member_model is not None:
                    subagent_config["model"] = member_model
                custom_subagents.append(subagent_config)

            logger.info(
                f"[TeamAgent] Built {len(custom_subagents)} role subagents for team '{team.name}'"
            )
        except ValueError as e:
            if str(e) in {
                "team_member_model_unavailable",
                "team_member_model_not_allowed",
            }:
                raise
            logger.error(f"[TeamAgent] Failed to build team subagents: {e}")
            raise ValueError("team_subagents_unavailable") from e
        except Exception as e:
            logger.error(f"[TeamAgent] Failed to build team subagents: {e}")
            raise ValueError("team_subagents_unavailable") from e

    # Fallback: built-in specialist subagents when no explicit team is selected
    if not custom_subagents:
        subagent_prompt_sections = [
            s
            for s in (
                *persona_sections,
                skills_prompt,
                memory_guide,
                subagent_runtime_section,
            )
            if s
        ]
        custom_subagents = [
            {
                "name": "general-purpose",
                "description": "General-purpose agent for researching complex questions, searching for files and content, and executing multi-step tasks. When you are searching for a keyword or file and are not confident that you will find the right match in the first few tries use this agent to perform the search for you. This agent has access to all tools as the main agent.",
                "system_prompt": SUBAGENT_PROMPT,
                "middleware": _build_subagent_middleware(
                    "general-purpose",
                    prompt_sections=subagent_prompt_sections,
                ),
            },
            {
                "name": "codebase-investigator",
                "description": SPECIALIZED_SUBAGENT_DESCRIPTIONS["codebase-investigator"],
                "system_prompt": CODEBASE_INVESTIGATOR_PROMPT,
                "middleware": _build_subagent_middleware(
                    "codebase-investigator",
                    prompt_sections=subagent_prompt_sections,
                ),
            },
            {
                "name": "implementation-worker",
                "description": SPECIALIZED_SUBAGENT_DESCRIPTIONS["implementation-worker"],
                "system_prompt": IMPLEMENTATION_WORKER_PROMPT,
                "middleware": _build_subagent_middleware(
                    "implementation-worker",
                    prompt_sections=subagent_prompt_sections,
                ),
            },
            {
                "name": "verification-runner",
                "description": SPECIALIZED_SUBAGENT_DESCRIPTIONS["verification-runner"],
                "system_prompt": VERIFICATION_RUNNER_PROMPT,
                "middleware": _build_subagent_middleware(
                    "verification-runner",
                    prompt_sections=subagent_prompt_sections,
                ),
            },
            {
                "name": "researcher",
                "description": SPECIALIZED_SUBAGENT_DESCRIPTIONS["researcher"],
                "system_prompt": RESEARCH_SUBAGENT_PROMPT,
                "middleware": _build_subagent_middleware(
                    "researcher",
                    prompt_sections=subagent_prompt_sections,
                ),
            },
        ]

    # ── 主代理中间件栈 ──
    user_middleware = create_retry_middleware(
        fallback_model=fallback_model_value, thinking=thinking_config
    )
    if team:
        user_middleware.append(TeamRouterDelegationGuardMiddleware())
        user_middleware.append(TaskDelegationEnvelopeMiddleware())
    user_middleware.append(ToolResultBinaryMiddleware(base_url=subagent_base_url))
    user_middleware.append(ArtifactDeliveryMiddleware(workspace_path=sandbox_work_dir))
    if image_url_to_base64:
        user_middleware.append(ImageUrlToBase64Middleware())
    _prompt_sections = [
        s
        for s in (
            *MAIN_AGENT_PROMPT_SECTIONS,
            *persona_sections,
            router_skills_prompt,
            memory_guide,
        )
        if s
    ]
    if sandbox_backend and sandbox_work_dir:
        _prompt_sections.append(SEARCH_SANDBOX_RUNTIME_SECTION.format(work_dir=sandbox_work_dir))
    active_goal = configurable.get("active_goal")
    goal_section = build_goal_prompt_section(active_goal)
    if goal_section:
        _prompt_sections.append(goal_section)
    if configurable.get("auto_mode"):
        _prompt_sections.append(AUTO_MODE_PROMPT_SECTION)
    if _prompt_sections:
        user_middleware.append(SectionPromptMiddleware(sections=_prompt_sections))
    if sandbox_backend:
        user_middleware.append(
            SandboxMCPMiddleware(backend=sandbox_backend, user_id=context.user_id or "default")
        )
        user_middleware.append(EnvVarPromptMiddleware(user_id=context.user_id or "default"))
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

    rubric_middleware = create_goal_rubric_middleware(
        model=llm,
        goal=active_goal,
        fallback_model=fallback_model_value,
        thinking=thinking_config,
    )
    user_middleware.extend(create_code_interpreter_middleware(agent_options))
    if rubric_middleware is not None:
        user_middleware.append(rubric_middleware)

    user_middleware.append(MainAgentContextMiddleware(backend=backend))
    user_middleware.append(SubagentResultHandoffMiddleware(backend=backend))

    user_middleware.append(PromptCachingMiddleware())

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
    logger.debug(f"[TeamAgent] Graph compile: {graph_compile_time * 1000:.3f}ms")
    team_subagent_names = {
        str(subagent.get("name"))
        for subagent in custom_subagents
        if isinstance(subagent, dict) and subagent.get("name")
    }
    team_delegation_event_count = 0

    inner_config: RunnableConfig = {
        "configurable": build_nested_graph_configurable(
            thread_id=state.get("session_id", str(uuid.uuid4())),
            checkpointer=inner_checkpointer,
            backend=backend,
            context=context,
            disabled_skills=configurable.get("disabled_skills"),
            enabled_skills=runtime_enabled_skills,
            base_url=configurable.get("base_url", ""),
            session_id=state.get("session_id"),
            trace_id=getattr(presenter, "trace_id", None),
            presenter=presenter,
            attachments=attachments,
        ),
        "recursion_limit": config.get("recursion_limit", settings.SESSION_MAX_RUNS_PER_SESSION),
    }

    # 构建传入的新消息（包含附件）
    recommendation_input = configurable.get("recommendation_input") or user_input
    if supports_vision:
        attachments = await inline_image_attachments_as_data_urls(
            attachments,
            base_url=configurable.get("base_url", ""),
            force_data_url=image_url_to_base64,
        )
    new_message = build_human_message(user_input, attachments, supports_vision=supports_vision)

    # 创建事件处理器
    logger.info("[TeamAgent] Creating AgentEventProcessor")
    event_processor = AgentEventProcessor(
        presenter,
        base_url=configurable.get("base_url", ""),
        subagent_display_names=subagent_display_names,
        subagent_avatars=subagent_avatars,
    )

    if recommendation_input and settings.ENABLE_RECOMMEND_QUESTIONS:
        from src.agents.core.recommendations import schedule_recommend_questions_from_state

        schedule_recommend_questions_from_state(
            presenter,
            recommendation_input,
            inner_graph,
            inner_config,
        )

    logger.info("[TeamAgent] Starting astream_events")
    try:
        async with isolated_nested_graph_run():
            async for event in inner_graph.astream_events(  # type: ignore[call-overload]
                build_goal_input(new_message, active_goal, rubric_middleware=rubric_middleware),
                inner_config,
                version="v2",
            ):
                if _is_team_delegation_event(event, team_subagent_names):
                    team_delegation_event_count += 1
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
    logger.info("[TeamAgent] astream_events completed")
    _raise_if_team_router_completed_without_required_delegation(
        team=team,
        user_input=user_input,
        delegation_event_count=team_delegation_event_count,
    )

    if settings.ENABLE_MEMORY and context.user_id:
        from src.infra.memory.tools import schedule_auto_memory_capture

        schedule_auto_memory_capture(context.user_id, user_input)

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
        except Exception:
            pass

    output_text = event_processor.output_text
    event_processor.clear()

    return {"output": output_text}
