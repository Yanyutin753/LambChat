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
        # PyMongo Async 的 find() 同步返回 cursor（仅 to_list 是 awaitable），fake 保持一致
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


@pytest.fixture(autouse=True)
def account_authority(monkeypatch):
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    from src.infra.user.storage import UserStorage

    user = SimpleNamespace(is_active=True, auth_version=None, pat_version=None)
    monkeypatch.setattr(UserStorage, "get_by_id", AsyncMock(return_value=user))
    return user


async def test_security_rotation_rejects_legacy_pat_and_hides_it_from_active_list(
    storage, account_authority
):
    token, _ = await storage.create(user_id="u1", name="legacy", scopes=["sandbox:execute"])
    # Simulate a record issued before versioned PATs existed.
    storage._get_collection().docs[0].pop("pat_version", None)
    account_authority.pat_version = "enrolled"
    assert await storage.verify(token) == (None, "revoked")
    assert await storage.list_for_user("u1") == []


async def test_new_pairing_works_until_next_recovery_rotation(storage, account_authority):
    account_authority.pat_version = "enrolled"
    token, _ = await storage.create(user_id="u1", name="new", scopes=["sandbox:execute"])
    assert (await storage.verify(token))[0] is not None
    account_authority.pat_version = "regenerated"
    assert await storage.verify(token) == (None, "revoked")


async def test_old_login_cannot_mint_pat_for_new_security_version(storage, account_authority):
    from src.kernel.errors import AppError

    account_authority.auth_version = "new-login"
    account_authority.pat_version = "new-pairing"
    with pytest.raises(AppError):
        await storage.create(
            user_id="u1", name="racing", scopes=["sandbox:execute"], auth_version="old-login"
        )
    assert storage._get_collection().docs == []


async def test_pat_insert_racing_rotation_is_already_invalid(storage, account_authority):
    coll = storage._get_collection()
    original = coll.insert_one

    async def rotate_then_insert(doc):
        account_authority.pat_version = "rotated"
        await original(doc)

    coll.insert_one = rotate_then_insert
    token, _ = await storage.create(user_id="u1", name="racing", scopes=["sandbox:execute"])
    assert await storage.verify(token) == (None, "revoked")


async def test_disabled_or_deleted_account_cannot_use_pat(storage, account_authority):
    token, _ = await storage.create(user_id="u1", name="test", scopes=["sandbox:execute"])
    account_authority.is_active = False
    assert await storage.verify(token) == (None, "revoked")


async def test_other_account_rotation_does_not_revoke_unenrolled_users_pat(storage, monkeypatch):
    from types import SimpleNamespace

    from src.infra.user.storage import UserStorage

    accounts = {
        "u1": SimpleNamespace(is_active=True, auth_version=None, pat_version=None),
        "u2": SimpleNamespace(is_active=True, auth_version=None, pat_version=None),
    }

    async def get_user(_self, user_id):
        return accounts[user_id]

    monkeypatch.setattr(UserStorage, "get_by_id", get_user)
    first, _ = await storage.create(user_id="u1", name="first", scopes=["sandbox:execute"])
    other, _ = await storage.create(user_id="u2", name="other", scopes=["sandbox:execute"])
    accounts["u1"].pat_version = "rotated"
    assert await storage.verify(first) == (None, "revoked")
    assert (await storage.verify(other))[0] is not None


async def test_enabled_account_cannot_mint_pat_with_only_a_valid_session(
    storage, account_authority
):
    from src.kernel.errors import AppError

    account_authority.two_factor_enabled = True
    with pytest.raises(AppError) as failure:
        await storage.create(user_id="u1", name="paired", scopes=["sandbox:execute"])
    assert failure.value.error_code.code == "two_factor_required"
    assert storage._get_collection().docs == []


async def test_each_pat_consumes_a_fresh_factor(storage, account_authority, monkeypatch):
    from unittest.mock import AsyncMock

    from src.infra.auth import two_factor as mfa
    from src.kernel.errors import AppError, ErrorCode

    account_authority.id = "u1"
    account_authority.two_factor_enabled = True
    verify = AsyncMock(side_effect=[None, AppError(ErrorCode.TWO_FACTOR_INVALID)])
    monkeypatch.setattr("src.infra.auth.pat.rate_limit", AsyncMock())
    monkeypatch.setattr(mfa.TwoFactorService, "verify_factor", verify)
    await storage.create(user_id="u1", name="first", scopes=[], code="123456")
    with pytest.raises(AppError):
        await storage.create(user_id="u1", name="replay", scopes=[], code="123456")
    assert len(storage._get_collection().docs) == 1
    assert verify.await_count == 2
