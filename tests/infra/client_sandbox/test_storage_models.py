from __future__ import annotations

from datetime import UTC, datetime, timedelta

from src.infra.client_sandbox.models import (
    ClientSandboxBindingCreate,
    ClientSandboxDeviceRegister,
    ClientSandboxRpcResponse,
)


def test_device_register_normalizes_workspace_root() -> None:
    device = ClientSandboxDeviceRegister(
        device_id="desktop-1",
        name="Workstation",
        platform="tauri",
        os="linux",
        app_version="2.5.3",
        workspace_root="/tmp/lambchat/",
        capabilities={"execute": True, "grep": True},
    )

    assert device.workspace_root == "/tmp/lambchat"
    assert device.capabilities["execute"] is True


def test_binding_create_defaults_to_future_expiry() -> None:
    before = datetime.now(UTC)
    binding = ClientSandboxBindingCreate(
        session_id="session-1",
        device_id="desktop-1",
        workspace_root="/tmp/workspace",
    )

    assert binding.status == "active"
    assert binding.expires_at > before + timedelta(hours=11)


def test_rpc_response_requires_result_or_error() -> None:
    response = ClientSandboxRpcResponse(
        request_id="rpc-1",
        ok=True,
        result={"output": "done", "exit_code": 0, "truncated": False},
    )

    assert response.error is None
    assert response.result["exit_code"] == 0
