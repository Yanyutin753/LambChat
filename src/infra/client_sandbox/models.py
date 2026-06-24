"""Models for desktop client sandbox registration, binding, and RPC."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

CLIENT_SANDBOX_BINDING_TTL_HOURS = 12


def utc_now() -> datetime:
    return datetime.now(UTC)


def default_binding_expiry() -> datetime:
    return utc_now() + timedelta(hours=CLIENT_SANDBOX_BINDING_TTL_HOURS)


class ClientSandboxDeviceRegister(BaseModel):
    device_id: str = Field(min_length=1, max_length=128)
    name: str = Field(min_length=1, max_length=200)
    platform: Literal["tauri"]
    os: str = Field(default="", max_length=64)
    app_version: str = Field(default="", max_length=64)
    workspace_root: str = Field(min_length=1)
    capabilities: dict[str, bool] = Field(default_factory=dict)

    @field_validator("workspace_root")
    @classmethod
    def normalize_workspace_root(cls, value: str) -> str:
        normalized = value.strip().rstrip("/")
        return normalized or "/"


class ClientSandboxDevice(ClientSandboxDeviceRegister):
    user_id: str
    last_seen_at: datetime = Field(default_factory=utc_now)
    created_at: datetime = Field(default_factory=utc_now)
    revoked_at: datetime | None = None


class ClientSandboxPreferenceUpdate(BaseModel):
    enabled: bool = True
    device_id: str = Field(min_length=1, max_length=128)
    workspace_root: str = Field(min_length=1)

    @field_validator("workspace_root")
    @classmethod
    def normalize_workspace_root(cls, value: str) -> str:
        normalized = value.strip().rstrip("/")
        return normalized or "/"


class ClientSandboxPreference(ClientSandboxPreferenceUpdate):
    user_id: str
    updated_at: datetime = Field(default_factory=utc_now)


class ClientSandboxBindingCreate(BaseModel):
    session_id: str = Field(min_length=1, max_length=128)
    device_id: str = Field(min_length=1, max_length=128)
    workspace_root: str = Field(min_length=1)
    status: Literal["active"] = "active"
    expires_at: datetime = Field(default_factory=default_binding_expiry)

    @field_validator("workspace_root")
    @classmethod
    def normalize_workspace_root(cls, value: str) -> str:
        normalized = value.strip().rstrip("/")
        return normalized or "/"


class ClientSandboxSessionBinding(ClientSandboxBindingCreate):
    user_id: str
    created_at: datetime = Field(default_factory=utc_now)
    ended_at: datetime | None = None

    @property
    def is_active(self) -> bool:
        return self.status == "active" and self.ended_at is None and self.expires_at > utc_now()


class ClientSandboxRpcError(BaseModel):
    code: str
    message: str


class ClientSandboxRpcRequest(BaseModel):
    type: Literal["client_sandbox:request"] = "client_sandbox:request"
    request_id: str
    session_id: str
    operation: str
    timeout_seconds: int
    payload: dict[str, Any] = Field(default_factory=dict)


class ClientSandboxRpcResponse(BaseModel):
    type: Literal["client_sandbox:response"] = "client_sandbox:response"
    request_id: str
    ok: bool
    result: dict[str, Any] | None = None
    error: ClientSandboxRpcError | None = None

    @model_validator(mode="after")
    def require_result_or_error(self) -> "ClientSandboxRpcResponse":
        if self.ok and self.result is None:
            raise ValueError("successful RPC response requires result")
        if not self.ok and self.error is None:
            raise ValueError("failed RPC response requires error")
        return self
