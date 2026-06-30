import json
from types import SimpleNamespace

import pytest

from src.kernel.schemas.persona_preset import (
    PersonaPreset,
    PersonaPresetScope,
    PersonaPresetStatus,
    PersonaPresetUpdate,
    PersonaPresetVisibility,
)
from src.kernel.schemas.user import TokenPayload


class _Runtime:
    def __init__(self, user_id: str | None) -> None:
        context = SimpleNamespace(user_id=user_id) if user_id is not None else None
        self.config = {"configurable": {"context": context}}


def _preset(
    preset_id: str,
    *,
    name: str = "动画师",
    scope: str = "user",
    visibility: str = "private",
    status: str = "draft",
) -> PersonaPreset:
    return PersonaPreset(
        id=preset_id,
        scope=scope,
        owner_user_id="admin-1" if scope == "user" else None,
        name=name,
        description="",
        avatar=None,
        tags=[],
        system_prompt="Animate with care.",
        starter_prompts=[],
        skill_names=[],
        visibility=visibility,
        status=status,
        version=1,
        usage_count=0,
        created_by="admin-1",
        updated_by="admin-1",
    )


def _admin_user() -> TokenPayload:
    return TokenPayload(
        sub="admin-1",
        username="admin",
        roles=["admin"],
        permissions=[
            "persona_preset:read",
            "persona_preset:write",
            "persona_preset:admin",
        ],
    )


def test_save_persona_preset_description_guides_create_and_update() -> None:
    from src.infra.tool import persona_preset_tool

    tools = persona_preset_tool.get_persona_preset_tools()
    description = persona_preset_tool.save_persona_preset.description
    create_fields = persona_preset_tool.save_persona_preset.args_schema.model_fields

    assert [tool.name for tool in tools] == ["save_persona_preset"]
    assert "Create or update" in description
    assert "create_agent_team" in description
    assert "preset_id" in description
    assert "current_name" in description
    assert "emoji or avatar image URL" in create_fields["avatar"].description
    assert "Optional persona id to update" in create_fields["preset_id"].description


@pytest.mark.asyncio
async def test_save_persona_preset_creates_and_offloads_result_json(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.infra.tool import persona_preset_tool

    calls: list[object] = []

    class FakeManager:
        async def create_preset(self, *args, **kwargs):
            return _preset("preset-1")

    async def fake_resolve_user(user_id: str) -> TokenPayload:
        assert user_id == "admin-1"
        return _admin_user()

    async def fake_run_blocking_io(func, *args, **kwargs):
        calls.append(func)
        return func(*args, **kwargs)

    monkeypatch.setattr(persona_preset_tool, "_resolve_user", fake_resolve_user)
    monkeypatch.setattr(persona_preset_tool, "PersonaPresetManager", FakeManager)
    monkeypatch.setattr(
        persona_preset_tool,
        "run_blocking_io",
        fake_run_blocking_io,
        raising=False,
    )

    result = json.loads(
        await persona_preset_tool.save_persona_preset.coroutine(
            name="动画师",
            system_prompt="Animate with care.",
            runtime=_Runtime("admin-1"),
        )
    )

    assert result["success"] is True
    assert result["entity_type"] == "persona_preset"
    assert result["action"] == "created"
    assert json.dumps in calls


@pytest.mark.asyncio
async def test_save_persona_preset_offloads_error_result_json(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.infra.tool import persona_preset_tool

    calls: list[object] = []

    async def fake_run_blocking_io(func, *args, **kwargs):
        calls.append(func)
        return func(*args, **kwargs)

    monkeypatch.setattr(
        persona_preset_tool,
        "run_blocking_io",
        fake_run_blocking_io,
        raising=False,
    )

    result = json.loads(
        await persona_preset_tool.save_persona_preset.coroutine(
            name="动画师",
            system_prompt="Animate with care.",
            runtime=_Runtime(None),
        )
    )

    assert result == {"error": "No user context available"}
    assert json.dumps in calls


@pytest.mark.asyncio
async def test_save_persona_preset_promotes_named_user_preset_to_global(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.infra.tool import persona_preset_tool

    calls: list[tuple[str, object]] = []
    dump_calls: list[object] = []

    class FakeManager:
        async def list_presets(self, **kwargs):
            calls.append(("list", kwargs))
            return [_preset("preset-1")]

        async def update_preset(
            self,
            preset_id: str,
            update_data: PersonaPresetUpdate,
            *,
            user_id: str,
            is_admin: bool,
        ):
            calls.append(("update", (preset_id, update_data, user_id, is_admin)))
            return _preset(
                preset_id,
                scope="global",
                visibility="public",
                status="published",
            )

    async def fake_resolve_user(user_id: str) -> TokenPayload:
        assert user_id == "admin-1"
        return _admin_user()

    async def fake_run_blocking_io(func, *args, **kwargs):
        dump_calls.append(func)
        return func(*args, **kwargs)

    monkeypatch.setattr(persona_preset_tool, "_resolve_user", fake_resolve_user)
    monkeypatch.setattr(persona_preset_tool, "PersonaPresetManager", FakeManager)
    monkeypatch.setattr(
        persona_preset_tool,
        "run_blocking_io",
        fake_run_blocking_io,
        raising=False,
    )

    result = json.loads(
        await persona_preset_tool.save_persona_preset.coroutine(
            current_name="动画师",
            scope="global",
            runtime=_Runtime("admin-1"),
        )
    )

    assert result["success"] is True
    assert result["entity_type"] == "persona_preset"
    assert result["action"] == "updated"
    assert result["preset"]["scope"] == "global"
    assert result["preset"]["visibility"] == "public"
    assert result["preset"]["status"] == "published"
    assert json.dumps in dump_calls

    assert calls[0][0] == "list"
    assert calls[0][1]["q"] == "动画师"
    assert calls[0][1]["scope"] == "user"

    update_call = calls[1][1]
    assert update_call[0] == "preset-1"
    assert update_call[1].scope == PersonaPresetScope.GLOBAL
    assert update_call[1].visibility == PersonaPresetVisibility.PUBLIC
    assert update_call[1].status == PersonaPresetStatus.PUBLISHED
    assert update_call[2] == "admin-1"
    assert update_call[3] is True
