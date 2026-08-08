"""Metadata-only search tool for progressively disclosed Skills."""

from __future__ import annotations

from typing import Any

from langchain_core.tools import BaseTool
from pydantic import BaseModel, Field, PrivateAttr

from src.infra.search import DiscoveryRecord, search_records

SKILL_SEARCH_LIMIT = 10


class SkillSearchInput(BaseModel):
    query: str = Field(
        ...,
        description="Skill name or capability; supports +required and select:ExactName.",
    )


def _normalize_tags(value: Any) -> tuple[str, ...]:
    if isinstance(value, str):
        return tuple(item.strip() for item in value.replace(";", ",").split(",") if item.strip())
    if isinstance(value, (list, tuple, set)):
        return tuple(str(item).strip() for item in value if str(item).strip())
    return ()


class SkillSearchTool(BaseTool):
    """Search filtered Skill metadata without reading instructions or mutating state."""

    name: str = "search_skills"
    description: str = (
        "Finds available Skills by exact name, capability, tag, Chinese pinyin, or initials. "
        "Returns metadata and the SKILL.md path to read."
    )
    args_schema: type[BaseModel] = SkillSearchInput
    _records: tuple[DiscoveryRecord, ...] = PrivateAttr(default=())

    def __init__(self, skills: list[dict], **kwargs: Any) -> None:
        super().__init__(**kwargs)
        unique: dict[str, dict] = {}
        for skill in skills:
            name = str(skill.get("name") or "").strip()
            if name and name not in unique:
                unique[name] = skill
        self._records = tuple(
            DiscoveryRecord(
                name=name,
                text=str(unique[name].get("description") or ""),
                tags=_normalize_tags(unique[name].get("tags")),
                payload={
                    "name": name,
                    "description": str(unique[name].get("description") or ""),
                    "tags": _normalize_tags(unique[name].get("tags")),
                },
            )
            for name in sorted(unique, key=lambda item: (item.lower(), item))
        )

    def _run(self, query: str) -> str:
        if not query.strip():
            return "Enter a Skill name or capability to search."
        if not self._records:
            return "No Skills are available."
        matches = search_records(query, list(self._records), max_results=SKILL_SEARCH_LIMIT)
        if not matches:
            return "No Skills matched that query."

        entries: list[str] = []
        for match in matches:
            metadata = match.payload
            description = metadata["description"] or "No description"
            tags = ", ".join(metadata["tags"])
            lines = [
                f"Name: {match.name}",
                f"Description: {description}",
                f"Path: /skills/{match.name}/SKILL.md",
            ]
            if tags:
                lines.append(f"Tags: {tags}")
            entries.append("\n".join(lines))
        return (
            "Read the matching SKILL.md with read_file before using the Skill.\n\n"
            + "\n\n".join(entries)
        )

    async def _arun(self, query: str) -> str:
        return self._run(query)
