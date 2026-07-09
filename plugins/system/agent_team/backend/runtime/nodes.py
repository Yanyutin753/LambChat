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
    "完整抖音策划",
)
_FULL_ASSET_PACKAGE_STAGE_TRIGGERS = (
    "分镜",
    "提示词",
    "首帧",
    "交付",
    "四阶段",
    "素材包流程",
    "文案",
    "图生视频",
    "多片段",
)
_TEAM_META_REQUEST_MARKERS = (
    "任务范围",
    "团队成员",
    "团队配置",
    "团队能力",
    "介绍团队",
    "说明团队",
)
_SUBSTANTIVE_REQUEST_MARKERS = (
    "生成",
    "创建",
    "制作",
    "写",
    "策划",
    "方案",
    "执行",
    "完成",
    "交付",
    "整理",
    "输出",
    "首帧",
    "文案",
    "提示词",
    "素材包",
)
_TEAM_ROUTER_DELEGATION_ATTEMPTS = 2

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
    if "抖音策划" in text and any(trigger in text for trigger in ("完整", "首帧", "文案")):
        return True
    return "素材包" in text and any(
        trigger in text for trigger in _FULL_ASSET_PACKAGE_STAGE_TRIGGERS
    )


def _is_team_meta_request(user_input: Any) -> bool:
    text = str(user_input or "").casefold()
    return bool(text) and any(marker in text for marker in _TEAM_META_REQUEST_MARKERS)


def _is_substantive_team_request(user_input: Any) -> bool:
    text = str(user_input or "").casefold().strip()
    if not text or _is_team_meta_request(text):
        return False
    if len(text) >= 24:
        return True
    return any(marker in text for marker in _SUBSTANTIVE_REQUEST_MARKERS)


def _get_team_router_required_delegation_reason(*, team: Any, user_input: Any) -> str | None:
    if not team or not getattr(team, "active_members", None):
        return None
    if _is_full_asset_package_request(user_input):
        return "full_asset_package"
    if _is_substantive_team_request(user_input):
        return "substantive_team_request"
    return None


def _build_team_router_delegation_retry_input(*, user_input: Any, reason: str) -> str:
    return (
        "团队路由恢复指令：上一轮只输出了路由计划或普通文本，但没有调用 `task` "
        "工具委派任何团队成员，因此不能视为完成。\n"
        f"保护原因：{reason}。\n"
        "现在必须先调用 `task` 工具，把实际工作分派给至少一名活跃团队成员；"
        "如果是多阶段素材、策划、首帧图、文案或交付任务，请按依赖顺序委派对应角色。"
        "在至少一次 `task` 调用完成前，不要输出最终答复。\n\n"
        f"原始用户请求：\n{str(user_input or '').strip()}"
    )


def _select_forced_delegation_members(
    *,
    team: Any,
    reason: str | None,
    delegated_subagent_names: set[str] | None = None,
) -> list[Any]:
    members = list(getattr(team, "active_members", []) or [])
    if not members:
        return []
    delegated = delegated_subagent_names or set()
    if reason == "full_asset_package":
        return [
            member for member in members if build_team_member_subagent_type(member) not in delegated
        ]
    if delegated:
        return []
    default_member_id = getattr(team, "default_member_id", None)
    if default_member_id:
        default_member = next((m for m in members if m.member_id == default_member_id), None)
        if default_member is not None:
            return [default_member]
    return [members[0]]


def _build_forced_delegation_description(
    *,
    team: Any,
    member: Any,
    user_input: Any,
    reason: str,
    index: int,
    total: int,
    previous_results: list[tuple[str, str]],
) -> str:
    role_name = getattr(member, "role_name", None) or build_team_member_subagent_type(member)
    prior = "\n\n".join(
        f"### Previous result from {name}\n{result.strip()}"
        for name, result in previous_results
        if result.strip()
    )
    prior_section = prior or "No previous member result yet. Start from the original request."
    return (
        "Team router forced delegation recovery.\n"
        f"Reason: {reason}.\n"
        f"Team: {getattr(team, 'name', '')}.\n"
        f"Current member: {role_name} ({index}/{total}).\n\n"
        "Original user request:\n"
        f"{str(user_input or '').strip()}\n\n"
        "Previous member results:\n"
        f"{prior_section}\n\n"
        "Assignment:\n"
        "- Complete the concrete portion of the request that matches your role.\n"
        "- For a complete short-video/material package, produce actual deliverable content, "
        "not just a plan.\n"
        "- Include clear handoff details for the next member when useful.\n"
        "- If you are the final member, include a concise final package summary and any "
        "artifact or image-generation status you can verify.\n"
    )


def _extract_forced_delegation_text(result: Any) -> str:
    if not isinstance(result, dict):
        return str(result or "").strip()
    messages = result.get("messages")
    if not isinstance(messages, list):
        return str(result or "").strip()
    for message in reversed(messages):
        content = getattr(message, "content", None)
        if isinstance(content, str) and content.strip():
            return content.strip()
        if isinstance(content, list):
            parts: list[str] = []
            for block in content:
                if isinstance(block, dict):
                    text = block.get("text") or block.get("content")
                    if text:
                        parts.append(str(text))
                elif block:
                    parts.append(str(block))
            joined = "".join(parts).strip()
            if joined:
                return joined
    return ""


def _append_processor_output(event_processor: Any, text: str) -> None:
    append = getattr(event_processor, "_append_output_text", None)
    if callable(append):
        append(text)


async def _emit_presenter_event(presenter: Any, event: dict[str, Any] | None) -> None:
    if not event:
        return
    emit = getattr(presenter, "emit", None)
    if callable(emit):
        await emit(event)


async def _emit_forced_delegation_text(
    *,
    presenter: Any,
    event_processor: Any,
    text: str,
) -> None:
    if not text:
        return
    await event_processor.flush()
    _append_processor_output(event_processor, text)
    emit_text = getattr(presenter, "emit_text", None)
    if callable(emit_text):
        await emit_text(text)
        return
    present_text = getattr(presenter, "present_text", None)
    if callable(present_text):
        await _emit_presenter_event(presenter, present_text(text))


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


def _collect_team_delegation_subagents(event: Any, subagent_names: set[str]) -> set[str]:
    if not _is_team_delegation_event(event, subagent_names):
        return set()
    return _collect_event_tool_names(event) & subagent_names


def _raise_if_team_router_completed_without_required_delegation(
    *,
    team: Any,
    user_input: Any,
    delegation_event_count: int,
) -> None:
    if delegation_event_count > 0:
        return
    reason = _get_team_router_required_delegation_reason(team=team, user_input=user_input)
    if reason is None:
        return

    logger.warning(
        "[TeamAgent] Blocking router completion without delegation: reason=%s "
        "team_id=%s team_name=%s",
        reason,
        getattr(team, "id", None),
        getattr(team, "name", None),
    )
    raise ValueError(f"team_router_delegation_required:{reason}")


async def _run_forced_team_delegation(
    *,
    team: Any,
    user_input: Any,
    reason: str,
    custom_subagents: list[SubAgent | CompiledSubAgent],
    llm: Any,
    backend: Any,
    filtered_tools: Any,
    inner_checkpointer: Any,
    store: Any,
    context: TeamAgentContext,
    presenter: Any,
    event_processor: Any,
    subagent_display_names: dict[str, str],
    subagent_avatars: dict[str, str],
    configurable: dict[str, Any],
    attachments: list[Any],
    config: RunnableConfig,
    delegated_subagent_names: set[str] | None = None,
) -> int:
    members = _select_forced_delegation_members(
        team=team,
        reason=reason,
        delegated_subagent_names=delegated_subagent_names,
    )
    if not members:
        return 0

    subagents_by_name = {
        str(subagent.get("name")): subagent
        for subagent in custom_subagents
        if isinstance(subagent, dict) and subagent.get("name")
    }
    previous_results: list[tuple[str, str]] = []
    emitted_results: list[tuple[str, str]] = []
    session_id = configurable.get("session_id") or ""

    logger.warning(
        "[TeamAgent] Forcing team delegation after router zero-delegation: "
        "reason=%s team_id=%s team_name=%s members=%d",
        reason,
        getattr(team, "id", None),
        getattr(team, "name", None),
        len(members),
    )

    for index, member in enumerate(members, start=1):
        subagent_type = build_team_member_subagent_type(member)
        subagent = subagents_by_name.get(subagent_type)
        if not subagent:
            logger.warning(
                "[TeamAgent] Forced delegation skipped missing subagent: type=%s",
                subagent_type,
            )
            continue

        role_name = getattr(member, "role_name", None) or subagent_type
        agent_instance_id = f"forced_{subagent_type}_{uuid.uuid4().hex[:8]}"
        description = _build_forced_delegation_description(
            team=team,
            member=member,
            user_input=user_input,
            reason=reason,
            index=index,
            total=len(members),
            previous_results=previous_results,
        )

        present_call = getattr(presenter, "present_agent_call", None)
        if callable(present_call):
            await _emit_presenter_event(
                presenter,
                present_call(
                    agent_id=agent_instance_id,
                    agent_name=subagent_display_names.get(subagent_type, role_name),
                    input_message=description,
                    depth=1,
                    agent_avatar=subagent_avatars.get(subagent_type),
                ),
            )

        try:
            forced_model: Any = subagent.get("model", llm)
            forced_system_prompt = str(subagent.get("system_prompt") or SUBAGENT_PROMPT)
            forced_middleware_value = subagent.get("middleware", [])
            forced_middleware = (
                list(forced_middleware_value)
                if isinstance(forced_middleware_value, (list, tuple))
                else []
            )
            forced_graph = create_deep_agent(
                model=forced_model,
                system_prompt=forced_system_prompt,
                backend=backend,
                tools=filtered_tools,
                checkpointer=inner_checkpointer,
                store=store,
                skills=None,
                subagents=[],
                middleware=forced_middleware,
            )
            forced_config: RunnableConfig = {
                "configurable": build_nested_graph_configurable(
                    thread_id=(
                        f"{session_id}:forced:{subagent_type}:{uuid.uuid4().hex}"
                        if session_id
                        else f"forced:{subagent_type}:{uuid.uuid4().hex}"
                    ),
                    checkpointer=inner_checkpointer,
                    backend=backend,
                    context=context,
                    disabled_skills=configurable.get("disabled_skills"),
                    enabled_skills=None,
                    base_url=configurable.get("base_url", ""),
                    session_id=configurable.get("session_id"),
                    trace_id=getattr(presenter, "trace_id", None),
                    presenter=presenter,
                    attachments=attachments,
                ),
                "recursion_limit": config.get(
                    "recursion_limit",
                    settings.SESSION_MAX_RUNS_PER_SESSION,
                ),
            }
            result = await forced_graph.ainvoke(
                {"messages": [build_human_message(description, [], supports_vision=False)]},
                forced_config,
            )
            result_text = _extract_forced_delegation_text(result)
        except Exception as exc:
            present_result = getattr(presenter, "present_agent_result", None)
            if callable(present_result):
                await _emit_presenter_event(
                    presenter,
                    present_result(
                        agent_id=agent_instance_id,
                        result="",
                        success=False,
                        depth=1,
                        error=str(exc),
                    ),
                )
            raise

        present_result = getattr(presenter, "present_agent_result", None)
        if callable(present_result):
            await _emit_presenter_event(
                presenter,
                present_result(
                    agent_id=agent_instance_id,
                    result=result_text,
                    success=True,
                    depth=1,
                ),
            )
        previous_results.append((role_name, result_text))
        emitted_results.append((role_name, result_text))

    if emitted_results:
        forced_output = "\n\n".join(
            f"### {role_name}\n{result_text}" for role_name, result_text in emitted_results
        )
        await _emit_forced_delegation_text(
            presenter=presenter,
            event_processor=event_processor,
            text=f"\n\n{forced_output}",
        )

    return len(emitted_results)


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
    delegated_team_subagent_names: set[str] = set()

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
    required_delegation_reason = _get_team_router_required_delegation_reason(
        team=team,
        user_input=user_input,
    )
    try:
        async with isolated_nested_graph_run():
            for attempt in range(1, _TEAM_ROUTER_DELEGATION_ATTEMPTS + 1):
                attempt_message = new_message
                if attempt > 1 and required_delegation_reason is not None:
                    attempt_message = build_human_message(
                        _build_team_router_delegation_retry_input(
                            user_input=user_input,
                            reason=required_delegation_reason,
                        ),
                        [],
                        supports_vision=False,
                    )

                async for event in inner_graph.astream_events(  # type: ignore[call-overload]
                    build_goal_input(
                        attempt_message,
                        active_goal,
                        rubric_middleware=rubric_middleware,
                    ),
                    inner_config,
                    version="v2",
                ):
                    if _is_team_delegation_event(event, team_subagent_names):
                        team_delegation_event_count += 1
                        delegated_team_subagent_names.update(
                            _collect_team_delegation_subagents(event, team_subagent_names)
                        )
                    await event_processor.process_event(event)

                if (
                    required_delegation_reason is None
                    or team_delegation_event_count > 0
                    or attempt >= _TEAM_ROUTER_DELEGATION_ATTEMPTS
                ):
                    break

                logger.warning(
                    "[TeamAgent] Retrying router after zero-delegation completion: "
                    "reason=%s attempt=%d team_id=%s team_name=%s",
                    required_delegation_reason,
                    attempt,
                    getattr(team, "id", None),
                    getattr(team, "name", None),
                )

            forced_members = (
                _select_forced_delegation_members(
                    team=team,
                    reason=required_delegation_reason,
                    delegated_subagent_names=delegated_team_subagent_names,
                )
                if required_delegation_reason is not None
                else []
            )
            if forced_members:
                assert required_delegation_reason is not None
                forced_count = await _run_forced_team_delegation(
                    team=team,
                    user_input=user_input,
                    reason=required_delegation_reason,
                    custom_subagents=custom_subagents,
                    llm=llm,
                    backend=backend,
                    filtered_tools=filtered_tools,
                    inner_checkpointer=inner_checkpointer,
                    store=store,
                    context=context,
                    presenter=presenter,
                    event_processor=event_processor,
                    subagent_display_names=subagent_display_names,
                    subagent_avatars=subagent_avatars,
                    configurable={
                        **configurable,
                        "session_id": state.get("session_id"),
                    },
                    attachments=attachments,
                    config=config,
                    delegated_subagent_names=delegated_team_subagent_names,
                )
                team_delegation_event_count += forced_count
                delegated_team_subagent_names.update(
                    build_team_member_subagent_type(member) for member in forced_members
                )
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
