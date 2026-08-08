import pytest

from src.infra.skill.loader import build_skills_prompt, load_skill_files


@pytest.mark.asyncio
async def test_build_skills_prompt_requires_transfer_before_execution() -> None:
    prompt = await build_skills_prompt(
        [{"name": "demo-skill", "description": "Run a demo script."}]
    )

    assert "Transfer executable files to the workspace" in prompt
    assert "`transfer_file` or `transfer_path`" in prompt


@pytest.mark.asyncio
async def test_small_skill_inventory_has_compact_guidance() -> None:
    prompt = await build_skills_prompt(
        [
            {"name": "alpha", "description": "Alpha capability"},
            {"name": "beta", "description": "Beta capability"},
            {"name": "gamma", "description": "Gamma capability"},
        ]
    )

    assert len(prompt) <= 560
    assert "search_skills" in prompt
    assert "SKILL.md" in prompt
    assert "transfer_file" in prompt


@pytest.mark.asyncio
async def test_twenty_skills_keep_every_name_and_description() -> None:
    skills = [
        {"name": f"skill-{index:02d}", "description": f"Description {index}"} for index in range(20)
    ]

    prompt = await build_skills_prompt(skills)

    assert all(skill["name"] in prompt for skill in skills)
    assert all(skill["description"] in prompt for skill in skills)


@pytest.mark.asyncio
async def test_twenty_one_skills_keep_all_names_without_descriptions_or_paths() -> None:
    skills = [
        {"name": f"skill-{index:02d}", "description": f"Private description {index}"}
        for index in range(21)
    ]

    prompt = await build_skills_prompt(skills)

    assert all(skill["name"] in prompt for skill in skills)
    assert all(skill["description"] not in prompt for skill in skills)
    assert "/skills/skill-" not in prompt
    assert "search_skills" in prompt
    assert "SKILL.md" in prompt
    assert "not shown" not in prompt


@pytest.mark.asyncio
async def test_load_skill_files_uses_async_binary_ref_parser(monkeypatch) -> None:
    calls: list[str] = []

    class _SkillManager:
        def __init__(self, user_id):
            self.user_id = user_id

        async def get_effective_skills(self):
            return {
                "demo": {
                    "enabled": True,
                    "description": "Demo skill",
                    "files": {"SKILL.md": "hello"},
                }
            }

    async def fake_parse_binary_ref_async(content: str):
        calls.append(content)
        return None

    monkeypatch.setattr("src.infra.skill.loader.settings.ENABLE_SKILLS", True)
    monkeypatch.setattr("src.infra.skill.manager.SkillManager", _SkillManager)
    monkeypatch.setattr(
        "src.infra.skill.loader.parse_binary_ref_async",
        fake_parse_binary_ref_async,
        raising=False,
    )

    result = await load_skill_files("user-1")

    assert calls == ["hello"]
    assert "/demo/SKILL.md" in result["files"]
