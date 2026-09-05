"""PAT 存储层测试：创建/校验/撤销/过期/范围。"""

from datetime import datetime, timedelta, timezone

import pytest

from src.infra.auth.pat import PAT_PREFIX, PATStorage


class _FakeCollection:
    def __init__(self):
        self.docs: list[dict] = []

    async def insert_one(self, doc: dict) -> None:
        self.docs.append(doc)

    async def find_one(self, query: dict) -> dict | None:
        for doc in self.docs:
            if all(doc.get(k) == v for k, v in query.items()):
                return doc
        return None

    def find(self, query: dict) -> "_FakeCursor":
        # motor 的 find() 同步返回 cursor（仅 to_list 是 awaitable），fake 保持一致
        return _FakeCursor([d for d in self.docs if all(d.get(k) == v for k, v in query.items())])

    async def update_one(self, query: dict, update: dict) -> None:
        doc = await self.find_one(query)
        if doc:
            doc.update(update.get("$set", {}))


class _FakeCursor:
    def __init__(self, docs: list[dict]):
        self._docs = docs

    def sort(self, key: str, direction: int) -> "_FakeCursor":
        self._docs = sorted(self._docs, key=lambda d: d.get(key), reverse=direction == -1)
        return self

    async def to_list(self, length: int | None = None) -> list[dict]:
        return self._docs


@pytest.fixture
def storage(monkeypatch) -> PATStorage:
    coll = _FakeCollection()
    st = PATStorage()
    monkeypatch.setattr(st, "_get_collection", lambda: coll)
    return st


async def test_create_returns_token_and_verifies(storage):
    token, record = await storage.create(user_id="u1", name="桌面端", scopes=["sandbox:execute"])
    assert token.startswith(PAT_PREFIX) and len(token) > 40
    verified, reason = await storage.verify(token)
    assert verified is not None and reason is None
    assert verified.user_id == "u1"
    assert verified.scopes == ["sandbox:execute"]


async def test_verify_rejects_unknown_token(storage):
    verified, reason = await storage.verify(f"{PAT_PREFIX}nope")
    assert verified is None and reason == "unknown"


async def test_revoke_makes_token_invalid(storage):
    token, record = await storage.create(user_id="u1", name="a", scopes=["sandbox:execute"])
    assert await storage.revoke(user_id="u1", pat_id=record.pat_id) is True
    verified, reason = await storage.verify(token)
    assert verified is None and reason == "revoked"


async def test_revoke_by_token_self_revokes_exactly_once(storage):
    """自删端点路径：按 token 明文吊销自身，重复吊销返回 False。"""
    token, _record = await storage.create(user_id="u1", name="shell", scopes=["sandbox:execute"])
    assert await storage.revoke_by_token(token) is True
    verified, reason = await storage.verify(token)
    assert verified is None and reason == "revoked"
    # 已吊销 / 未知 token → False（幂等拒绝）
    assert await storage.revoke_by_token(token) is False
    assert await storage.revoke_by_token("lc_pat_never_issued") is False


async def test_expired_token_rejected(storage):
    token, _ = await storage.create(
        user_id="u1",
        name="a",
        scopes=["sandbox:execute"],
        expires_at=datetime.now(timezone.utc) - timedelta(hours=1),
    )
    verified, reason = await storage.verify(token)
    assert verified is None and reason == "expired"


async def test_list_for_user_excludes_revoked(storage):
    await storage.create(user_id="u1", name="a", scopes=["sandbox:execute"])
    _, rec2 = await storage.create(user_id="u1", name="b", scopes=["sandbox:execute"])
    await storage.revoke(user_id="u1", pat_id=rec2.pat_id)
    listed = await storage.list_for_user("u1")
    assert [p.name for p in listed] == ["a"]


async def test_touch_last_used(storage):
    token, record = await storage.create(user_id="u1", name="a", scopes=["sandbox:execute"])
    await storage.touch_last_used(record.pat_id)
    verified, _reason = await storage.verify(token)
    assert verified.last_used_at is not None
