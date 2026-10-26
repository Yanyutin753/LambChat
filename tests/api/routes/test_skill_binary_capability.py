from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.api.routes import skill
from src.infra.skill.binary import build_binary_ref_content
from src.kernel.errors import AppError


async def test_owned_skill_preview_returns_key_bound_capability(monkeypatch):
    monkeypatch.setattr(
        "src.kernel.config.settings.JWT_SECRET_KEY", "test-secret-for-owned-skill-file"
    )
    key = "skills/owner/demo/clip.mp4"
    storage = SimpleNamespace(
        get_skill_file=AsyncMock(return_value=build_binary_ref_content(key, "video/mp4", 3))
    )
    result = await skill.get_skill_file("demo", "clip.mp4", SimpleNamespace(sub="owner"), storage)
    assert "file_token=" in result["url"]


async def test_forged_skill_reference_cannot_sign_another_owners_file():
    storage = SimpleNamespace(
        get_skill_file=AsyncMock(
            return_value=build_binary_ref_content("image/other/private.png", "image/png", 3)
        )
    )
    with pytest.raises(AppError):
        await skill.get_skill_file("demo", "clip.png", SimpleNamespace(sub="owner"), storage)
