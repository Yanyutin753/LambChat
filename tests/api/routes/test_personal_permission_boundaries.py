"""Personal capabilities reject requests before touching owner-scoped storage."""

from unittest.mock import patch

import httpx
import pytest
from fastapi import FastAPI

from src.api.deps import get_current_user_required
from src.api.error_handlers import register_error_handlers
from src.api.routes import bookmark, memory, project, revealed_file, session, team
from src.kernel.errors import AppError, ErrorCode
from src.kernel.schemas.user import TokenPayload


@pytest.mark.parametrize(
    ("module", "method", "path", "payload"),
    [
        (session, "GET", "", None),
        (session, "DELETE", "/owned", None),
        (project, "GET", "", None),
        (project, "DELETE", "/owned?delete_sessions=true", None),
        (team, "GET", "/", None),
        (team, "DELETE", "/owned", None),
        (memory, "GET", "/", None),
        (memory, "DELETE", "/owned", None),
        (bookmark, "GET", "/bookmarks/", None),
        (revealed_file, "GET", "/revealed", None),
    ],
)
async def test_personal_endpoints_require_capability(module, method, path, payload):
    app = FastAPI()
    register_error_handlers(app)
    app.include_router(module.router, prefix="/resource")
    app.dependency_overrides[get_current_user_required] = lambda: TokenPayload(
        sub="owner", username="owner", roles=[], permissions=[]
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.request(
            method, "/resource" + path, json=payload, follow_redirects=True
        )
    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "permission_missing"


async def test_project_cascade_requires_session_delete_before_storage():
    user = TokenPayload(sub="owner", username="owner", permissions=["project:delete"])
    with patch.object(project, "get_project_storage") as storage:
        with pytest.raises(AppError) as denied:
            await project.delete_project("owned", delete_sessions=True, user=user)
    assert denied.value.error_code == ErrorCode.PERMISSION_MISSING
    storage.assert_not_called()


@pytest.mark.parametrize("path", ["/one/install", "/one/update"])
async def test_marketplace_reader_cannot_install_or_update_skills(path):
    from src.api.routes import marketplace

    app = FastAPI()
    register_error_handlers(app)
    app.include_router(marketplace.router, prefix="/resource")
    app.dependency_overrides[get_current_user_required] = lambda: TokenPayload(
        sub="owner", username="owner", permissions=["marketplace:read"]
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post("/resource" + path)
    assert response.status_code == 403
    assert response.json()["detail"]["args"]["permission"] == "skill:write"


async def test_sandbox_pat_scope_does_not_replace_role_permission(monkeypatch):
    from unittest.mock import AsyncMock

    from src.api.routes import sandbox

    monkeypatch.setattr(sandbox, "has_tool_permission", AsyncMock(return_value=False))
    check = sandbox._require_sandbox_permission("sandbox:manage")
    with pytest.raises(AppError) as denied:
        await check(TokenPayload(sub="owner", username="owner", permissions=["sandbox:read"]))
    assert denied.value.error_code == ErrorCode.PERMISSION_MISSING
