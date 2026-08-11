"""Mongo-authoritative owner leases for session clear-group releases."""

from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any

from bson import ObjectId

from src.infra.utils.datetime import utc_now

ATTACHMENT_CLEAR_RELEASE_LEASE_TTL = timedelta(minutes=2)
ATTACHMENT_CLEAR_RELEASE_HEARTBEAT_SECONDS = 30.0
_ATTACHMENT_CLEAR_RELEASE_EPOCH_ID = "attachment_clear_release_epoch"


class SessionClearReleaseOperationsMixin:
    """Release-owner fencing composed into session attachment operations."""

    if TYPE_CHECKING:
        collection: Any
        attachment_metadata_collection: Any

    async def claim_attachment_clear_group_release(
        self,
        session_id: str,
        operation_id: str,
        group_id: str,
        owner_token: str,
    ) -> dict[str, Any] | None:
        """Bind a globally ordered, expiring owner fence to one deleted group."""
        field = "attachment_clear_operation"
        group_path = f"{field}.groups.{group_id}"
        now = utc_now()

        async def _find(identity: dict[str, Any]) -> dict[str, Any] | None:
            return await self.collection.find_one(
                {**identity, f"{field}.id": operation_id},
                {group_path: 1},
            )

        identities: list[dict[str, Any]] = [{"session_id": session_id}]
        try:
            identities.append({"_id": ObjectId(session_id)})
        except Exception:
            pass
        identity: dict[str, Any] | None = None
        document: dict[str, Any] | None = None
        for candidate in identities:
            document = await _find(candidate)
            if document is not None:
                identity = candidate
                break
        if identity is None or document is None:
            return None
        group = (
            document.get(field, {}).get("groups", {}).get(group_id)
            if isinstance(document.get(field), dict)
            else None
        )
        if not isinstance(group, dict):
            return None
        current_epoch = group.get("release_owner_epoch")
        if (
            group.get("status") == "releasing"
            and group.get("release_owner_token") == owner_token
            and isinstance(current_epoch, int)
            and current_epoch > 0
        ):
            if await self.renew_attachment_clear_group_release(
                session_id,
                operation_id,
                group_id,
                owner_token=owner_token,
                owner_epoch=current_epoch,
            ):
                return {"token": owner_token, "epoch": current_epoch}
            return None

        if group.get("status") == "releasing":
            expires_at = group.get("release_owner_expires_at")
            if not isinstance(expires_at, datetime) or expires_at > now:
                return None
        elif group.get("status") != "deleted":
            return None

        metadata = self.attachment_metadata_collection
        if isinstance(current_epoch, int) and current_epoch > 0:
            await metadata.update_one(
                {"_id": _ATTACHMENT_CLEAR_RELEASE_EPOCH_ID},
                {"$max": {"epoch": current_epoch}},
                upsert=True,
            )
        epoch_record = await metadata.find_one_and_update(
            {"_id": _ATTACHMENT_CLEAR_RELEASE_EPOCH_ID},
            {"$inc": {"epoch": 1}},
            upsert=True,
            return_document=True,
        )
        epoch = epoch_record.get("epoch") if epoch_record else None
        if not isinstance(epoch, int) or epoch < 1:
            raise RuntimeError("attachment clear release epoch allocation failed")

        snapshot: dict[str, Any] = {f"{group_path}.status": group["status"]}
        for name in (
            "release_owner_token",
            "release_owner_epoch",
            "release_owner_expires_at",
        ):
            snapshot[f"{group_path}.{name}"] = group[name] if name in group else {"$exists": False}
        query = {**identity, f"{field}.id": operation_id, **snapshot}
        binding = {
            f"{group_path}.status": "releasing",
            f"{group_path}.release_owner_token": owner_token,
            f"{group_path}.release_owner_epoch": epoch,
            f"{group_path}.release_owner_expires_at": now + ATTACHMENT_CLEAR_RELEASE_LEASE_TTL,
            "updated_at": now,
        }
        try:
            result = await self.collection.find_one_and_update(
                query,
                {"$set": binding},
                return_document=True,
            )
        except Exception:
            result = await self.collection.find_one(
                {
                    **identity,
                    f"{field}.id": operation_id,
                    f"{group_path}.status": "releasing",
                    f"{group_path}.release_owner_token": owner_token,
                    f"{group_path}.release_owner_epoch": epoch,
                },
                {group_path: 1},
            )
            if result is None:
                raise
        if result is None:
            return None
        return {"token": owner_token, "epoch": epoch}

    async def renew_attachment_clear_group_release(
        self,
        session_id: str,
        operation_id: str,
        group_id: str,
        *,
        owner_token: str,
        owner_epoch: int,
    ) -> bool:
        """Renew only the exact live release owner."""
        field = "attachment_clear_operation"
        group_path = f"{field}.groups.{group_id}"
        update = {
            "$set": {
                f"{group_path}.release_owner_expires_at": utc_now()
                + ATTACHMENT_CLEAR_RELEASE_LEASE_TTL,
                "updated_at": utc_now(),
            }
        }
        result = await self.collection.update_one(
            {
                "session_id": session_id,
                f"{field}.id": operation_id,
                f"{group_path}.status": "releasing",
                f"{group_path}.release_owner_token": owner_token,
                f"{group_path}.release_owner_epoch": owner_epoch,
            },
            update,
        )
        if result.modified_count > 0:
            return True
        try:
            result = await self.collection.update_one(
                {
                    "_id": ObjectId(session_id),
                    f"{field}.id": operation_id,
                    f"{group_path}.status": "releasing",
                    f"{group_path}.release_owner_token": owner_token,
                    f"{group_path}.release_owner_epoch": owner_epoch,
                },
                update,
            )
            return result.modified_count > 0
        except Exception:
            return False
