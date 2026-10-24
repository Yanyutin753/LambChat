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
        "persona_preset:delete",
        "persona_preset:admin",
    }


def test_default_roles_include_persona_preset_permissions() -> None:
    roles = {role["name"]: role for role in RBACManager().get_default_roles()}

    assert Permission.PERSONA_PRESET_READ.value in roles["user"]["permissions"]
    assert Permission.PERSONA_PRESET_WRITE.value in roles["user"]["permissions"]
    assert Permission.PERSONA_PRESET_ADMIN.value not in roles["user"]["permissions"]
    assert Permission.PERSONA_PRESET_READ.value in roles["guest"]["permissions"]
    assert Permission.PERSONA_PRESET_ADMIN.value in roles["admin"]["permissions"]


def test_scheduled_task_permissions_exist_and_are_grouped() -> None:
    assert Permission.SCHEDULED_TASK_READ.value == "scheduled_task:read"
    assert Permission.SCHEDULED_TASK_WRITE.value == "scheduled_task:write"
    assert Permission.SCHEDULED_TASK_DELETE.value == "scheduled_task:delete"

    response = get_permissions_response()
    grouped_values = {
        permission.value
        for group in response.groups
        if group.name == "定时任务"
        for permission in group.permissions
    }

    assert grouped_values == {
        "scheduled_task:read",
        "scheduled_task:write",
        "scheduled_task:delete",
    }


def test_default_user_role_includes_scheduled_task_permissions() -> None:
    roles = {role["name"]: role for role in RBACManager().get_default_roles()}

    assert Permission.SCHEDULED_TASK_READ.value in roles["user"]["permissions"]
    assert Permission.SCHEDULED_TASK_WRITE.value in roles["user"]["permissions"]
    assert Permission.SCHEDULED_TASK_DELETE.value in roles["user"]["permissions"]
    assert Permission.SCHEDULED_TASK_READ.value not in roles["guest"]["permissions"]
    assert Permission.SCHEDULED_TASK_READ.value in roles["admin"]["permissions"]


def test_usage_permissions_exist_and_are_grouped() -> None:
    assert Permission.USAGE_READ.value == "usage:read"
    assert Permission.USAGE_ADMIN.value == "usage:admin"

    response = get_permissions_response()
    grouped_values = {
        permission.value
        for group in response.groups
        if group.name == "用量统计"
        for permission in group.permissions
    }

    assert grouped_values == {
        "usage:read",
        "usage:admin",
        "usage:quota_manage",
    }


def test_persona_preset_create_defaults_to_user_private_draft() -> None:
    data = PersonaPresetCreate(name="Coder", system_prompt="Be precise.")

    assert data.scope == PersonaPresetScope.USER
    assert data.visibility == "private"
    assert data.status == "draft"
    assert data.tags == []
    assert data.skill_names == []
