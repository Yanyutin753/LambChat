"""PAT 个人访问令牌存储：明文只在创建时返回，库中仅存 SHA-256 哈希。"""

import hashlib
import secrets
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from pydantic import BaseModel

from src.kernel.config import settings

PAT_PREFIX = "lc_pat_"
_COLL_PATS = "pats"


class PATRecord(BaseModel):
    pat_id: str
    user_id: str
    name: str
    scopes: list[str]
    token_hash: str
    prefix: str
    created_at: datetime
    expires_at: Optional[datetime] = None
    last_used_at: Optional[datetime] = None
    revoked: bool = False


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class PATStorage:
    def __init__(self) -> None:
        self._collection: Optional[Any] = None

    def _get_collection(self):
        if self._collection is None:
            from src.infra.storage.mongodb import get_mongo_client

            client = get_mongo_client()
            db = client[settings.MONGODB_DB]
            self._collection = db[_COLL_PATS]
        return self._collection

    async def ensure_indexes(self) -> None:
        coll = self._get_collection()
        await coll.create_index("pat_id", unique=True)
        await coll.create_index("token_hash", unique=True)
        await coll.create_index("user_id")

    async def create(
        self,
        *,
        user_id: str,
        name: str,
        scopes: list[str],
        expires_at: Optional[datetime] = None,
    ) -> tuple[str, PATRecord]:
        token = f"{PAT_PREFIX}{secrets.token_urlsafe(32)}"
        record = PATRecord(
            pat_id=uuid.uuid4().hex,
            user_id=user_id,
            name=name,
            scopes=scopes,
            token_hash=_hash_token(token),
            prefix=token[:12],
            created_at=_utcnow(),
            expires_at=expires_at,
        )
        await self._get_collection().insert_one(record.model_dump())
        return token, record

    async def verify(self, token: str) -> tuple[Optional[PATRecord], Optional[str]]:
        """校验 token。

        有效 -> ``(record, None)``；失败 -> ``(None, reason)``，
        reason ∈ {"unknown", "revoked", "expired"}（调用方据此区分 PAT_EXPIRED 等错误码）。
        """
        doc = await self._get_collection().find_one({"token_hash": _hash_token(token)})
        if doc is None:
            return None, "unknown"
        if doc.get("revoked"):
            return None, "revoked"
        expires_at = doc.get("expires_at")
        if expires_at is not None and expires_at <= _utcnow():
            return None, "expired"
        return PATRecord(**doc), None

    async def list_for_user(self, user_id: str) -> list[PATRecord]:
        cursor = self._get_collection().find({"user_id": user_id, "revoked": False})
        docs = await cursor.sort("created_at", -1).to_list(None)
        return [PATRecord(**d) for d in docs]

    async def revoke(self, *, user_id: str, pat_id: str) -> bool:
        doc = await self._get_collection().find_one({"pat_id": pat_id, "user_id": user_id})
        if doc is None:
            return False
        await self._get_collection().update_one({"pat_id": pat_id}, {"$set": {"revoked": True}})
        return True

    async def touch_last_used(self, pat_id: str) -> None:
        await self._get_collection().update_one(
            {"pat_id": pat_id}, {"$set": {"last_used_at": _utcnow()}}
        )
