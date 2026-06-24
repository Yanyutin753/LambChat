"""MongoDB storage for client sandbox devices and session bindings."""

from __future__ import annotations

from typing import Any

from src.infra.client_sandbox.models import (
    ClientSandboxBindingCreate,
    ClientSandboxDevice,
    ClientSandboxDeviceRegister,
    ClientSandboxPreference,
    ClientSandboxPreferenceUpdate,
    ClientSandboxSessionBinding,
    utc_now,
)
from src.kernel.config import settings

DEVICE_COLLECTION = "client_sandbox_devices"
BINDING_COLLECTION = "client_sandbox_session_bindings"
PREFERENCE_COLLECTION = "client_sandbox_preferences"


class ClientSandboxStorage:
    def __init__(self) -> None:
        self._device_collection: Any = None
        self._binding_collection: Any = None
        self._preference_collection: Any = None

    @property
    def devices(self):
        if self._device_collection is None:
            from src.infra.storage.mongodb import get_mongo_client

            client = get_mongo_client()
            self._device_collection = client[settings.MONGODB_DB][DEVICE_COLLECTION]
        return self._device_collection

    @property
    def bindings(self):
        if self._binding_collection is None:
            from src.infra.storage.mongodb import get_mongo_client

            client = get_mongo_client()
            self._binding_collection = client[settings.MONGODB_DB][BINDING_COLLECTION]
        return self._binding_collection

    @property
    def preferences(self):
        if self._preference_collection is None:
            from src.infra.storage.mongodb import get_mongo_client

            client = get_mongo_client()
            self._preference_collection = client[settings.MONGODB_DB][PREFERENCE_COLLECTION]
        return self._preference_collection

    async def upsert_device(
        self,
        user_id: str,
        registration: ClientSandboxDeviceRegister,
    ) -> ClientSandboxDevice:
        now = utc_now()
        doc = registration.model_dump()
        doc.update({"user_id": user_id, "last_seen_at": now, "revoked_at": None})
        await self.devices.update_one(
            {"user_id": user_id, "device_id": registration.device_id},
            {"$set": doc, "$setOnInsert": {"created_at": now}},
            upsert=True,
        )
        saved = await self.devices.find_one(
            {"user_id": user_id, "device_id": registration.device_id}
        )
        return ClientSandboxDevice(**saved)

    async def list_devices(self, user_id: str) -> list[ClientSandboxDevice]:
        cursor = self.devices.find({"user_id": user_id, "revoked_at": None})
        return [ClientSandboxDevice(**doc) async for doc in cursor]

    async def set_preference(
        self,
        user_id: str,
        preference: ClientSandboxPreferenceUpdate,
    ) -> ClientSandboxPreference:
        now = utc_now()
        doc = preference.model_dump()
        doc.update({"user_id": user_id, "updated_at": now})
        await self.preferences.update_one(
            {"user_id": user_id},
            {"$set": doc},
            upsert=True,
        )
        saved = await self.preferences.find_one({"user_id": user_id})
        return ClientSandboxPreference(**saved)

    async def get_preference(self, user_id: str) -> ClientSandboxPreference | None:
        doc = await self.preferences.find_one({"user_id": user_id})
        return ClientSandboxPreference(**doc) if doc else None

    async def create_or_refresh_binding(
        self,
        user_id: str,
        binding: ClientSandboxBindingCreate,
    ) -> ClientSandboxSessionBinding:
        now = utc_now()
        doc = binding.model_dump()
        doc.update({"user_id": user_id, "ended_at": None})
        await self.bindings.update_one(
            {"user_id": user_id, "session_id": binding.session_id},
            {"$set": doc, "$setOnInsert": {"created_at": now}},
            upsert=True,
        )
        saved = await self.bindings.find_one({"user_id": user_id, "session_id": binding.session_id})
        return ClientSandboxSessionBinding(**saved)

    async def get_active_binding(
        self,
        user_id: str,
        session_id: str,
    ) -> ClientSandboxSessionBinding | None:
        doc = await self.bindings.find_one(
            {
                "user_id": user_id,
                "session_id": session_id,
                "status": "active",
                "ended_at": None,
            }
        )
        if not doc:
            return None
        binding = ClientSandboxSessionBinding(**doc)
        return binding if binding.is_active else None

    async def end_binding(self, user_id: str, session_id: str) -> bool:
        result = await self.bindings.update_one(
            {"user_id": user_id, "session_id": session_id, "ended_at": None},
            {"$set": {"status": "ended", "ended_at": utc_now()}},
        )
        return bool(getattr(result, "modified_count", 0))
