from __future__ import annotations

from src.infra.skill.skill_search_tool import SkillSearchTool


def _skills() -> list[dict]:
    return [
        {
            "name": "RedBookSkills",
            "description": "小红书内容发布与运营",
            "tags": ["社交媒体", "内容"],
            "content": "FULL BODY MUST NOT LEAK",
        },
        {
            "name": "database-query",
            "description": "Query relational databases",
            "tags": "sql,data",
        },
    ]


def test_search_skills_supports_exact_pinyin_initials_and_tags() -> None:
    tool = SkillSearchTool(_skills())

    assert "Name: RedBookSkills" in tool._run("select:redbookskills")
    assert "Name: RedBookSkills" in tool._run("xiaohongshu")
    assert "Name: RedBookSkills" in tool._run("xh")
    assert "Name: RedBookSkills" in tool._run("shejiaomeiti")
    assert "Name: database-query" in tool._run("sql")


def test_search_skills_returns_metadata_and_read_instruction_not_body() -> None:
    result = SkillSearchTool(_skills())._run("xiaohongshu")

    assert "Name: RedBookSkills" in result
    assert "Path: /skills/RedBookSkills/SKILL.md" in result
    assert "read" in result.lower()
    assert "FULL BODY MUST NOT LEAK" not in result


def test_search_skills_is_stable_and_capped_at_ten() -> None:
    skills = [
        {"name": f"skill-{index:02d}", "description": "shared capability"}
        for index in range(12, -1, -1)
    ]

    result = SkillSearchTool(skills)._run("shared")

    assert result.count("Name:") == 10
    assert result.index("Name: skill-00") < result.index("Name: skill-09")
    assert "Name: skill-10" not in result


def test_search_skills_handles_blank_empty_and_no_match_without_fabrication() -> None:
    assert SkillSearchTool(_skills())._run(" ") == "Enter a Skill name or capability to search."
    assert SkillSearchTool([])._run("image") == "No Skills are available."
    assert SkillSearchTool(_skills())._run("quantum-teleport") == "No Skills matched that query."
