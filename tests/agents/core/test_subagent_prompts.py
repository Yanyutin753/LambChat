from src.agents.core.prompt_policy import (
    ARTIFACT_POLICY,
    LAZY_SANDBOX_RUNTIME_POLICY,
    PERSISTENT_STORAGE_POLICY,
    SANDBOX_RUNTIME_POLICY,
    SANDBOX_STORAGE_POLICY,
)
from src.agents.core.subagent_prompts import (
    CODEBASE_INVESTIGATOR_PROMPT,
    DEFAULT_SUBAGENT_PROMPT,
    DETAILED_SUBAGENT_PROMPT,
    IMPLEMENTATION_WORKER_PROMPT,
    MAIN_AGENT_PROMPT_SECTIONS,
    RESEARCH_SUBAGENT_PROMPT,
    SPECIALIZED_SUBAGENT_NAMES,
    SUBAGENT_PROMPT,
    SUBAGENT_TASK_GUIDE,
    VERIFICATION_RUNNER_PROMPT,
    WORKFLOW_SECTION,
    build_response_language_section,
)
from src.agents.fast_agent.prompt import FAST_SYSTEM_PROMPT
from src.agents.search_agent.prompt import (
    DEFAULT_SYSTEM_PROMPT,
    SANDBOX_RUNTIME_SECTION,
    SANDBOX_SYSTEM_PROMPT,
)
from src.agents.team_agent.prompt import (
    SANDBOX_RUNTIME_SECTION as TEAM_SANDBOX_RUNTIME_SECTION,
)
from src.agents.team_agent.prompt import (
    SANDBOX_SYSTEM_PROMPT as TEAM_SANDBOX_SYSTEM_PROMPT,
)
from src.agents.team_agent.prompt import TEAM_ROUTER_SYSTEM_PROMPT


def _assert_markers(text: str, markers: tuple[str, ...]) -> None:
    lowered = text.lower()
    for marker in markers:
        assert marker.lower() in lowered


COMMON_WORKFLOW_MARKERS = (
    "current session workspace",
    "target exists",
    "auto-staged",
    "reveal_file",
    "returned url",
    "reveal_project",
    "completion gate",
    "timestamp",
    "untrusted",
    "ask_human",
    "verify",
    "external side effects",
    "privacy",
    "progress",
    "todo",
)


def test_workflow_policy_is_capability_agnostic_and_compact() -> None:
    _assert_markers(WORKFLOW_SECTION, COMMON_WORKFLOW_MARKERS)
    assert len(WORKFLOW_SECTION) <= 2400
    assert "### Project / Folder Reveal" not in WORKFLOW_SECTION
    assert "search_tools" not in WORKFLOW_SECTION
    assert "search_skills" not in WORKFLOW_SECTION
    assert "mcporter" not in WORKFLOW_SECTION
    assert "transfer_file" not in WORKFLOW_SECTION


def test_storage_and_subagent_policies_fit_compact_budgets() -> None:
    # 400：第三条存储位置（/workspace/.shared 持久目录）入册后的新预算
    assert len(SANDBOX_STORAGE_POLICY) <= 400
    assert len(SUBAGENT_TASK_GUIDE) <= 560


def test_main_prompts_compose_storage_and_canonical_workflow_once() -> None:
    persistent_prompts = (FAST_SYSTEM_PROMPT, DEFAULT_SYSTEM_PROMPT)
    sandbox_prompts = (SANDBOX_SYSTEM_PROMPT, TEAM_SANDBOX_SYSTEM_PROMPT)

    assert all(prompt == PERSISTENT_STORAGE_POLICY for prompt in persistent_prompts)
    assert all(prompt == SANDBOX_STORAGE_POLICY for prompt in sandbox_prompts)
    for base in (*persistent_prompts, *sandbox_prompts):
        effective = "\n\n".join((base, *MAIN_AGENT_PROMPT_SECTIONS))
        _assert_markers(effective, COMMON_WORKFLOW_MARKERS)
        assert effective.count("Artifact Completion Gate") == 1


def test_sandbox_storage_is_shared_and_runtime_path_is_separate() -> None:
    assert SANDBOX_SYSTEM_PROMPT == TEAM_SANDBOX_SYSTEM_PROMPT == SANDBOX_STORAGE_POLICY
    assert "{work_dir}" not in SANDBOX_SYSTEM_PROMPT
    assert SANDBOX_RUNTIME_SECTION == LAZY_SANDBOX_RUNTIME_POLICY
    assert TEAM_SANDBOX_RUNTIME_SECTION == SANDBOX_RUNTIME_POLICY
    assert "{work_dir}" in SANDBOX_RUNTIME_SECTION
    assert SANDBOX_SYSTEM_PROMPT.count("virtual Skill storage") == 1
    assert "transfer_file" not in SANDBOX_SYSTEM_PROMPT


def test_storage_and_runtime_policies_document_persistent_shared_dir() -> None:
    """/workspace/.shared 持久目录约定进全部沙箱策略（文件工具别名 + shell 变量）。"""
    for policy in (SANDBOX_STORAGE_POLICY, LAZY_SANDBOX_RUNTIME_POLICY, SANDBOX_RUNTIME_POLICY):
        assert "/workspace/.shared" in policy
    for runtime in (LAZY_SANDBOX_RUNTIME_POLICY, SANDBOX_RUNTIME_POLICY):
        assert "$LAMBCHAT_SHARED" in runtime


def test_search_lazy_runtime_distinguishes_file_and_shell_workspace_paths() -> None:
    rendered = SANDBOX_RUNTIME_SECTION.format(work_dir="/workspace/session-1")

    _assert_markers(
        rendered,
        (
            "Logical file-tool alias (not a shell path)",
            "/workspace/session-1",
            "Use this alias only with file tools and uploads",
            "relative paths",
            "$LAMBCHAT_WORKSPACE",
            "Never paste `/workspace/session-1` into a shell command",
            "Never guess or repeat a provider filesystem path",
        ),
    )


def test_search_lazy_runtime_documents_file_tool_shell_bridging() -> None:
    rendered = SANDBOX_RUNTIME_SECTION.format(work_dir="/workspace/session-1")

    # 文件工具与 shell 共享同一沙箱文件系统：alias 与 $LAMBCHAT_WORKSPACE 互为映射
    _assert_markers(
        rendered,
        (
            "same directory",
            "file-tool writes appear in the shell",
            "shell-created files are readable by file tools at `/workspace/session-1/<name>`",
            "outside the work directory",
            "never at a guessed `/workspace/<name>`",
        ),
    )
    # /skills 与 /memories 是文件工具专属的虚拟存储；可复用产物进持久共享目录，
    # 先 ls 检查避免每轮重复转移；一次性文件才进当前会话工作区
    _assert_markers(
        rendered,
        (
            "exist only for file tools",
            "transfer_path",
            "target prefix `/workspace/.shared/`",
            "$LAMBCHAT_SHARED",
            "persists across sessions",
        ),
    )
    # URL 下载要落到工作目录 alias，后续 shell 命令才能用
    _assert_markers(
        rendered,
        (
            "upload_url_to_sandbox",
            "pass `/workspace/session-1/<name>` as the target",
            "$LAMBCHAT_WORKSPACE",
        ),
    )
    # 桥接规则属于系统提示词，保持紧凑预算
    assert len(LAZY_SANDBOX_RUNTIME_POLICY) <= 1700


def test_team_runtime_keeps_eager_real_work_dir_semantics() -> None:
    real_work_dir = "/home/user/sessions/session-1"
    rendered = TEAM_SANDBOX_RUNTIME_SECTION.format(work_dir=real_work_dir)

    assert real_work_dir in rendered
    assert "Use this absolute, session-scoped path for shell/file output" in rendered
    assert "$LAMBCHAT_WORKSPACE" not in rendered


def test_team_nodes_use_team_owned_eager_runtime_section() -> None:
    from inspect import getsource

    from src.agents.team_agent import nodes as team_nodes

    source = getsource(team_nodes)
    assert "SANDBOX_RUNTIME_SECTION as TEAM_SANDBOX_RUNTIME_SECTION" in source
    assert "SANDBOX_RUNTIME_SECTION as SEARCH_SANDBOX_RUNTIME_SECTION" not in source


def test_artifact_policy_has_single_canonical_source() -> None:
    assert WORKFLOW_SECTION.count(ARTIFACT_POLICY) == 1
    assert WORKFLOW_SECTION.count("Artifact Completion Gate") == 1


def test_subagent_prompts_cover_workflow_and_structured_handoff() -> None:
    handoff = (
        "## Handoff Notes",
        "Goal:",
        "What I checked:",
        "Key findings:",
        "Files / tools touched:",
        "Risks / blockers:",
        "Suggested next step:",
    )
    for prompt in (DEFAULT_SUBAGENT_PROMPT, DETAILED_SUBAGENT_PROMPT, SUBAGENT_PROMPT):
        _assert_markers(prompt, COMMON_WORKFLOW_MARKERS + handoff)


def test_main_subagent_guide_covers_timestamp_dispatch_handoff_and_synthesis() -> None:
    _assert_markers(
        SUBAGENT_TASK_GUIDE,
        (
            "Current task start time:",
            "dispatch",
            "parallel",
            "handoff",
            "activity log",
            "synthesize",
            "deduplicate",
            "conflict",
        ),
    )


def test_team_router_keeps_role_dispatch_contract() -> None:
    _assert_markers(
        TEAM_ROUTER_SYSTEM_PROMPT,
        ("task", "timestamp", "dispatch", "handoff", "synthesize", "default role"),
    )


def test_specialist_prompts_keep_distinct_scopes() -> None:
    assert SPECIALIZED_SUBAGENT_NAMES == (
        "codebase-investigator",
        "implementation-worker",
        "verification-runner",
        "researcher",
    )
    _assert_markers(CODEBASE_INVESTIGATOR_PROMPT, ("do not edit", "relevant files"))
    _assert_markers(IMPLEMENTATION_WORKER_PROMPT, ("scoped", "verification"))
    _assert_markers(VERIFICATION_RUNNER_PROMPT, ("do not change production", "pass/fail"))
    _assert_markers(RESEARCH_SUBAGENT_PROMPT, ("primary sources", "date/version"))


def test_read_only_specialists_omit_artifact_delivery_policy() -> None:
    """只读子代理（investigator/verification/researcher）不向用户交付产物，
    Artifact Delivery/Completion Gate 是主 agent 与文件写入角色的职责——
    裁掉可省每次 spawn 约 500 字符；安全/工作区/进度纪律保留。
    """
    for prompt in (
        CODEBASE_INVESTIGATOR_PROMPT,
        VERIFICATION_RUNNER_PROMPT,
        RESEARCH_SUBAGENT_PROMPT,
    ):
        assert "auto-staged" not in prompt
        assert "reveal_file" not in prompt
        assert "reveal_project" not in prompt
        assert "Artifact Completion Gate" not in prompt
        # 保留的纪律：工作区边界 + 安全（untrusted/隐私）+ 进度
        _assert_markers(
            prompt,
            (
                "current session workspace",
                "target exists",
                "untrusted",
                "privacy",
                "Handoff Notes",
            ),
        )
        assert len(prompt) <= 2500


def test_writer_subagents_keep_artifact_delivery_policy() -> None:
    """文件写入角色（general-purpose / implementation-worker）保留交付纪律。"""
    for prompt in (SUBAGENT_PROMPT, IMPLEMENTATION_WORKER_PROMPT):
        _assert_markers(prompt, ("auto-staged", "reveal_project", "Artifact Completion Gate"))


def test_dynamic_prompt_middleware_order_is_canonical() -> None:
    from inspect import getsource

    from src.agents.search_agent.nodes import agent_node
    from src.agents.team_agent.nodes import team_router_node

    for node in (agent_node, team_router_node):
        source = getsource(node)
        env = source.rfind("EnvVarPromptMiddleware")
        deferred = source.rfind("ToolSearchMiddleware")
        assert -1 < env < deferred
        # 记忆索引只附着到 memory_recall 工具，不进入用户消息。
        assert "MemoryRecallIndexMiddleware" in source
        assert "PromptCachingMiddleware" not in source


def test_authored_prompt_sections_place_runtime_before_goal_and_mode() -> None:
    from inspect import getsource

    from src.agents.search_agent.nodes import agent_node
    from src.agents.team_agent.nodes import team_router_node

    for node in (agent_node, team_router_node):
        source = getsource(node)
        assembly = source.rfind("_prompt_sections = [")
        installation = source.rfind("SectionPromptMiddleware(sections=_prompt_sections)")

        assert -1 < assembly < installation
        # The session workspace path moved out of the system prompt onto the
        # file-tool descriptions (Codex-style layering); the middleware must
        # be installed after the env-var middleware it follows.
        env = source.rfind("EnvVarPromptMiddleware")
        sandbox = source.rfind("SandboxWorkspaceMiddleware")
        assert -1 < env < sandbox
        # Goal/auto-mode context is persisted into the user message at write
        # time (chat layer), never injected at request time by the agents.
        assert "goal_section" not in source
        assert "auto_section" not in source
        assert "TurnContextPromptMiddleware" not in source
        assert "VolatileSectionPromptMiddleware" not in source


def test_build_response_language_section_pins_ui_locale_with_exceptions() -> None:
    section = build_response_language_section("zh")

    assert "Simplified Chinese" in section
    # 界面语言优先于消息/引用内容语言（中文用户贴英文报错仍是中文回复），
    # 但保留显式例外（OpenAI 提示词指南：给出语言及其改变条件）
    assert "regardless of the language of the user's message or any quoted content" in section
    assert "explicitly requests" in section
    # 代码与报错原文不翻译
    assert "technical identifiers" in section


def test_build_response_language_section_covers_every_frontend_locale() -> None:
    for language in ("en", "zh", "ja", "ko", "ru"):
        assert build_response_language_section(language)


def test_build_response_language_section_ignores_unknown_or_missing_locale() -> None:
    # 无法识别界面语言时不注入提示段，保留模型跟随用户消息语言的默认行为
    assert build_response_language_section(None) == ""
    assert build_response_language_section("") == ""
    assert build_response_language_section("fr") == ""


def test_main_agent_nodes_wire_response_language_into_prompt_sections() -> None:
    from inspect import getsource

    from src.agents.fast_agent.nodes import fast_agent_node
    from src.agents.search_agent.nodes import agent_node
    from src.agents.team_agent.nodes import team_router_node

    for node in (fast_agent_node, agent_node, team_router_node):
        source = getsource(node)
        assert "build_response_language_section" in source, (
            f"{node.__name__} must inject the response language prompt section"
        )
        assert 'agent_options.get("response_language")' in source
