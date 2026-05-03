from __future__ import annotations

from src.infra.auth.rbac import RBACManager
from src.kernel.schemas.permission import get_permissions_response
from src.kernel.schemas.persona_preset import PersonaPresetCreate, PersonaPresetScope
from src.kernel.types import Permission


def test_persona_preset_permissions_exist_and_are_grouped() -> None:
    assert Permission.PERSONA_PRESET_READ.value == "persona_preset:read"
    assert Permission.PERSONA_PRESET_WRITE.value == "persona_preset:write"
    assert Permission.PERSONA_PRESET_ADMIN.value == "persona_preset:admin"

    response = get_permissions_response()
    grouped_values = {
        permission.value
        for group in response.groups
        if group.name == "角色预设"
        for permission in group.permissions
    }

    assert grouped_values == {
        "persona_preset:read",
        "persona_preset:write",
        "persona_preset:admin",
    }


def test_default_roles_include_persona_preset_permissions() -> None:
    roles = {role["name"]: role for role in RBACManager().get_default_roles()}

    assert Permission.PERSONA_PRESET_READ.value in roles["user"]["permissions"]
    assert Permission.PERSONA_PRESET_WRITE.value in roles["user"]["permissions"]
    assert Permission.PERSONA_PRESET_ADMIN.value not in roles["user"]["permissions"]
    assert Permission.PERSONA_PRESET_READ.value in roles["guest"]["permissions"]
    assert Permission.PERSONA_PRESET_ADMIN.value in roles["admin"]["permissions"]


def test_persona_preset_create_defaults_to_user_private_draft() -> None:
    data = PersonaPresetCreate(name="Coder", system_prompt="Be precise.")

    assert data.scope == PersonaPresetScope.USER
    assert data.visibility == "private"
    assert data.status == "draft"
    assert data.tags == []
    assert data.skill_names == []
