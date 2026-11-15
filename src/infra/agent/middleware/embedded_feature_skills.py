"""Add authorized feature guides to model input without changing system or history."""

from collections.abc import Awaitable, Callable, Collection
from functools import lru_cache
from pathlib import Path

from langchain.agents.middleware.types import AgentMiddleware, ModelRequest, ModelResponse
from langchain_core.messages import HumanMessage

from src.infra.skill.builtin import catalog


def _read_resource(directory: Path, filename: str) -> str:
    path = (directory / filename).resolve()
    if not path.is_relative_to(directory.resolve()):
        raise ValueError("Embedded feature skill resource must remain in its bundle")
    return path.read_text(encoding="utf-8")


def _tool_name(tool: object) -> str:
    if isinstance(tool, dict):
        definition = tool.get("function", tool) if tool.get("type") == "function" else tool
        name = definition.get("name") if isinstance(definition, dict) else None
    else:
        name = getattr(tool, "name", None)
    return name if isinstance(name, str) else ""


@lru_cache(maxsize=128)
def _load_guide(skill: catalog.BuiltinFeatureSkill, platform: str) -> str:
    content = _read_resource(skill.directory, "SKILL.md")
    if skill.platform_files:
        filename = dict(skill.platform_files).get(platform)
        content += "\n" + (
            _read_resource(skill.directory, filename) if filename else skill.unknown_platform_guide
        )
    return content


class EmbeddedFeatureSkillsMiddleware(AgentMiddleware):
    def __init__(self, *, capabilities: Collection[str] = (), platform: str = "") -> None:
        super().__init__()
        self._skills: list[catalog.BuiltinFeatureSkill] = []
        self._platform = platform
        seen: set[str] = set()
        for skill in catalog.BUILTIN_FEATURE_SKILLS:
            if skill.id in seen or not skill.required_tools:
                raise ValueError(
                    "Embedded feature skills need unique IDs and explicit tool requirements"
                )
            seen.add(skill.id)
            if not skill.required_capabilities.issubset(capabilities):
                continue
            self._skills.append(skill)

    async def awrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], Awaitable[ModelResponse]],
    ) -> ModelResponse:
        messages = [
            message
            for message in request.messages
            if not (
                message.name == "embedded_feature_skill"
                and message.additional_kwargs.get("lambchat_builtin_skill") is True
            )
        ]
        tools = {_tool_name(tool) for tool in request.tools}
        references = [
            HumanMessage(
                content=(
                    "Application-provided feature reference, not a user request. "
                    "This guide grants no permissions and does not override the user's task.\n\n"
                    + _load_guide(skill, self._platform)
                ),
                name="embedded_feature_skill",
                additional_kwargs={"lambchat_builtin_skill": True, "feature_skill_id": skill.id},
            )
            for skill in self._skills
            if skill.required_tools.issubset(tools)
        ]
        messages = [*references, *messages]
        if messages != request.messages:
            request = request.override(messages=messages)
        return await handler(request)
