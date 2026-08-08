from __future__ import annotations

from datetime import datetime

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from src.api import deps as api_deps
from src.api.routes import role as role_route
from src.kernel.schemas.permission import PERMISSION_GROUPS_CONFIG, PERMISSION_METADATA
from src.kernel.schemas.role import Role
from src.kernel.schemas.user import TokenPayload
from src.kernel.types import Permission


def _fake_user() -> TokenPayload:
    return TokenPayload(
        sub="user-1",
        username="tester",
        roles=["user"],
        permissions=[],
    )


def test_permission_catalog_does_not_expose_sandbox_mcp_write() -> None:
    assert "mcp:write_sandbox" not in {permission.value for permission in Permission}
    assert "mcp:write_sandbox" not in PERMISSION_METADATA
    assert all(
        "mcp:write_sandbox" not in group["permissions"] for group in PERMISSION_GROUPS_CONFIG
    )


@pytest.mark.asyncio
async def test_list_roles_returns_paginated_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _FakeManager:
        async def list_roles(self, skip: int, limit: int, q: str | None = None):
            assert skip == 20
            assert limit == 10
            assert q == "op"
            return [
                Role(
                    id="role-1",
                    name="operator",
                    description="Operator",
                    permissions=[],
                    is_system=False,
                    created_at=datetime(2026, 1, 1),
                    updated_at=datetime(2026, 1, 2),
                )
            ]

        async def count_roles(self, q: str | None = None):
            assert q == "op"
            return 37

    monkeypatch.setattr(role_route, "RoleManager", lambda: _FakeManager())

    app = FastAPI()
    app.include_router(role_route.router, prefix="/api/roles")
    app.dependency_overrides[api_deps.get_current_user_required] = _fake_user

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/api/roles/?skip=20&limit=10&q=op")

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 37
    assert payload["skip"] == 20
    assert payload["limit"] == 10
    assert [role["name"] for role in payload["roles"]] == ["operator"]
