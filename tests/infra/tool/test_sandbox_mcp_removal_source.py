from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def _source(relative_path: str) -> str:
    return (ROOT / relative_path).read_text(encoding="utf-8")


def test_agent_runtime_does_not_register_sandbox_mcp() -> None:
    paths = (
        "src/agents/fast_agent/context.py",
        "src/agents/search_agent/context.py",
        "src/agents/search_agent/nodes.py",
        "src/agents/team_agent/nodes.py",
        "src/api/routes/agent/__init__.py",
        "src/infra/agent/middleware/__init__.py",
        "src/infra/agent/middleware/prompt_injection.py",
    )

    for path in paths:
        source = _source(path)
        assert "sandbox_mcp" not in source.lower(), path
        assert "sandboxmcpmiddleware" not in source.lower(), path


def test_sandbox_lifecycle_does_not_rebuild_mcp() -> None:
    paths = (
        "src/infra/sandbox/_cubesandbox_helpers.py",
        "src/infra/sandbox/_daytona_helpers.py",
        "src/infra/sandbox/_e2b_helpers.py",
        "src/infra/sandbox/session_manager.py",
        "src/infra/envvar/sync.py",
        "src/infra/tool/env_var_tool.py",
    )

    for path in paths:
        source = _source(path)
        assert "ensure_sandbox_mcp" not in source, path


def test_runtime_guidance_and_cache_do_not_reference_mcporter() -> None:
    paths = (
        "src/agents/core/prompt_policy.py",
        "src/infra/agent/middleware/prompt_caching.py",
        "src/infra/agent/middleware/tool_interception.py",
        "src/infra/tool/cache_pubsub.py",
        "src/infra/tool/deferred_manager.py",
        "src/infra/tool/tool_search_tool.py",
        "tests/agents/core/test_system_prompt_budget.py",
    )

    for path in paths:
        source = _source(path)
        assert "mcporter" not in source.lower(), path
        assert "sandbox_mcp" not in source.lower(), path


def test_sandbox_templates_do_not_install_mcporter() -> None:
    for path in ("scripts/create_e2b_template.py", "scripts/create_daytona_snapshot.py"):
        assert "mcporter" not in _source(path).lower(), path


def test_runtime_settings_do_not_expose_sandbox_mcp_rebuild_concurrency() -> None:
    for path in ("src/kernel/config/base.py", "src/kernel/config/_definitions_sandbox.py"):
        assert "SANDBOX_MCP_REBUILD_CONCURRENCY" not in _source(path), path


def test_ordinary_sandbox_tools_remain_available() -> None:
    catalog = _source("src/api/routes/agent/__init__.py")

    for tool_name in ("read_file", "write_file", "edit_file", "ls", "glob", "grep"):
        assert f'name="{tool_name}"' in catalog
