from src.agents.core.subagent_prompts import build_role_subagent_prompt


def test_includes_role_identity():
    prompt = build_role_subagent_prompt(
        role_name="Research Analyst",
        role_system_prompt="You are a senior research analyst.",
    )
    assert "Research Analyst" in prompt
    assert "senior research analyst" in prompt
    assert "Handoff Notes" in prompt


def test_includes_shared_workflow():
    prompt = build_role_subagent_prompt(
        role_name="Writer",
        role_system_prompt="You are a technical writer.",
    )
    assert "Artifact Delivery" in prompt


def test_includes_team_context():
    prompt = build_role_subagent_prompt(
        role_name="Coder",
        role_system_prompt="You write code.",
        team_name="Dev Team",
        team_instructions="Focus on TypeScript.",
    )
    assert "Dev Team" in prompt
    assert "TypeScript" in prompt


def test_includes_role_instructions_as_system_constraints():
    prompt = build_role_subagent_prompt(
        role_name="Writer",
        role_system_prompt="You are a writer.",
        role_instructions="Always write in Xiaohongshu style with emoji.",
    )

    assert "### Role Instructions" in prompt
    assert "Always write in Xiaohongshu style with emoji." in prompt


def test_without_team_context():
    prompt = build_role_subagent_prompt(
        role_name="Coder",
        role_system_prompt="You write code.",
    )
    assert "Coder" in prompt
    assert "Handoff Notes" in prompt
