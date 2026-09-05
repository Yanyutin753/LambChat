"""云端沙箱确认策略的用户级来源（user.metadata.sandboxCloudConfirmPolicy）。

云端策略与本地不同：本地随 daemon 上报（注册表），云端存在用户 metadata，
由个人资料页配置。未设置/非法值归 none（保持云上历史行为），查询异常归
all（与本地门同样保守 fail-closed）。
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from src.infra.agent.middleware import sandbox_confirm
from src.infra.agent.middleware.sandbox_confirm import (
    _CloudPolicyResolver,
    _lookup_cloud_confirm_policy,
)


def _fake_user_storage(monkeypatch: pytest.MonkeyPatch, *, metadata, calls: list | None = None):
    class _FakeStorage:
        async def get_by_id(self, user_id: str):
            if calls is not None:
                calls.append(user_id)
            if isinstance(metadata, Exception):
                raise metadata
            if metadata is None:
                return None
            return SimpleNamespace(metadata=metadata)

    monkeypatch.setattr(sandbox_confirm, "_user_storage", _FakeStorage)


async def test_metadata_policy_returned(monkeypatch):
    _fake_user_storage(monkeypatch, metadata={"sandboxCloudConfirmPolicy": "commands"})
    assert await _lookup_cloud_confirm_policy("u1") == "commands"


async def test_unset_policy_defaults_to_none(monkeypatch):
    _fake_user_storage(monkeypatch, metadata={})
    assert await _lookup_cloud_confirm_policy("u1") == "none"


async def test_missing_user_defaults_to_none(monkeypatch):
    _fake_user_storage(monkeypatch, metadata=None)
    assert await _lookup_cloud_confirm_policy("u1") == "none"


async def test_invalid_policy_defaults_to_none(monkeypatch):
    _fake_user_storage(monkeypatch, metadata={"sandboxCloudConfirmPolicy": "yolo"})
    assert await _lookup_cloud_confirm_policy("u1") == "none"


async def test_lookup_failure_fails_closed_to_all(monkeypatch):
    _fake_user_storage(monkeypatch, metadata=RuntimeError("db down"))
    assert await _lookup_cloud_confirm_policy("u1") == "all"


async def test_resolver_caches_lookup_per_instance(monkeypatch):
    calls: list[str] = []
    _fake_user_storage(monkeypatch, metadata={"sandboxCloudConfirmPolicy": "all"}, calls=calls)
    resolver = _CloudPolicyResolver("u1")
    assert await resolver() == "all"
    assert await resolver() == "all"
    assert calls == ["u1"]
