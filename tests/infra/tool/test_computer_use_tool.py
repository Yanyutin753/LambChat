"""computer_use 工具单测:动作校验、payload 构建、结果格式化与错误收敛。"""

from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any

import pytest

from src.infra.tool import computer_use_tool as cut
from src.kernel.errors import AppError, ErrorCode


def _runtime(
    user_id: str = "u1", *, machine: str | None = "mac-staging-cua", platform="local"
) -> Any:
    return SimpleNamespace(
        config={
            "configurable": {
                "context": SimpleNamespace(user_id=user_id),
                "session_id": "session-1",
                "computer_use_context": {"platform": platform, "machine_id": machine},
            }
        }
    )


@pytest.fixture(autouse=True)
def unattended_policy(monkeypatch):
    async def lookup(user_id, machine_id=None):
        return "none"

    monkeypatch.setattr(cut, "_lookup_confirm_policy", lookup, raising=False)


async def _call(**kwargs: Any) -> str:
    merged = {"runtime": _runtime()}
    merged.update(kwargs)
    return await cut.computer_use.ainvoke(merged)


async def test_cua_uses_trusted_selected_machine_without_model_argument(monkeypatch):
    async def dispatch(user_id, op, payload, *, machine_id=None):
        return {"result": {"machine": machine_id}}

    monkeypatch.setattr(cut, "dispatch_local_call", dispatch)
    result = json.loads(await _call(action="apps", runtime=_runtime(machine="selected-mac")))
    assert result["machine"] == "selected-mac"


async def test_model_cannot_override_selected_machine(monkeypatch):
    async def dispatch(*args, **kwargs):
        pytest.fail("a different machine must never receive the call")

    monkeypatch.setattr(cut, "dispatch_local_call", dispatch)
    result = await _call(
        action="apps", machine_id="other-windows", runtime=_runtime(machine="selected-mac")
    )
    assert result.startswith("ERROR machine_mismatch")


async def test_selected_machine_is_not_replaced_by_account_default():
    assert await cut.resolve_computer_use_context(
        "u1",
        {
            "sandbox": "local",
            "sandbox_machine_id": "selected-windows",
        },
    ) == {"platform": "local", "machine_id": "selected-windows"}


async def test_automatic_selection_cannot_choose_a_cua_machine():
    assert await cut.resolve_computer_use_context("u1", {"sandbox": "local"}) == {
        "platform": "local",
        "machine_id": None,
    }


async def test_resuming_on_different_machine_is_denied_even_if_new_policy_none(monkeypatch):
    runtime = _runtime(machine="new-machine")
    runtime.tool_call_id = "call-1"
    runtime.config["configurable"]["computer_use_context"]["resume"] = {
        "tool_call_id": "call-1",
        "approved": True,
        "confirmation_context": {"machine_id": "old-machine", "operation_sha256": "old"},
    }

    async def dispatch(*args, **kwargs):
        pytest.fail("old approval must not reach a new machine with policy none")

    monkeypatch.setattr(cut, "dispatch_local_call", dispatch)
    assert "declined_by_user" in await _call(action="apps", runtime=runtime)


async def test_cua_dispatches_trusted_session_scope(monkeypatch):
    async def dispatch(user_id, op, payload, *, machine_id=None):
        assert payload["session_id"] == "session-1"
        assert machine_id == "mac-staging-cua"
        return {"result": {"ok": True}}

    monkeypatch.setattr(cut, "dispatch_local_call", dispatch)
    assert json.loads(await _call(action="apps"))["ok"] is True


async def test_commands_policy_requires_confirmation_for_screenshots(monkeypatch):
    async def lookup(*args):
        return "commands"

    async def dispatch(*args, **kwargs):
        pytest.fail("a screenshot cannot bypass the commands confirmation policy")

    monkeypatch.setattr(cut, "_lookup_confirm_policy", lookup)
    monkeypatch.setattr(cut, "dispatch_local_call", dispatch)
    assert "declined_by_user" in await _call(action="state", pid=42, include_screenshot=True)


@pytest.mark.parametrize(
    "runtime", [_runtime(machine=None), _runtime(platform="cloud"), SimpleNamespace(config={})]
)
async def test_missing_local_selection_never_falls_back_to_account_machine(monkeypatch, runtime):
    async def dispatch(*args, **kwargs):
        pytest.fail("no dispatch without trusted local machine selection")

    monkeypatch.setattr(cut, "dispatch_local_call", dispatch)
    result = await _call(action="apps", runtime=runtime)
    assert result.startswith("ERROR ")


async def test_cua_fails_closed_when_confirmation_required_without_interrupt(monkeypatch):
    async def lookup(user_id, machine_id=None):
        assert machine_id == "mac-staging-cua"
        return "all"

    async def dispatch(*args, **kwargs):
        pytest.fail("no desktop access without approval")

    monkeypatch.setattr(cut, "_lookup_confirm_policy", lookup, raising=False)
    monkeypatch.setattr(cut, "dispatch_local_call", dispatch)
    result = await _call(action="state", pid=42, include_screenshot=True)
    assert "declined_by_user" in result


@pytest.mark.asyncio
async def test_invalid_action_is_rejected_without_dispatch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    called = []

    async def _dispatch(*args: Any, **kwargs: Any) -> dict:
        called.append(args)
        return {"status": "ok", "result": {}}

    monkeypatch.setattr(cut, "dispatch_local_call", _dispatch)
    assert (await _call(action="hack")).startswith("ERROR invalid_action: choose one of")
    assert not called


@pytest.mark.asyncio
async def test_state_action_requires_pid_or_name(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cut, "dispatch_local_call", None)  # type: ignore[assignment]
    assert (await _call(action="state")).startswith("ERROR invalid_arguments")


@pytest.mark.asyncio
async def test_status_formats_plain_dict(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}

    async def _dispatch(user_id: str, op: str, payload: dict, *, machine_id=None) -> dict:
        captured.update(user_id=user_id, op=op, payload=payload)
        return {
            "status": "ok",
            "result": {"platform": "darwin", "ready": False, "accessibility": "denied"},
        }

    monkeypatch.setattr(cut, "dispatch_local_call", _dispatch)
    result = await _call(action="status")
    assert captured["op"] == "cua_status"
    assert captured["user_id"] == "u1"
    assert "darwin" in result


@pytest.mark.asyncio
async def test_state_returns_rendered_tree(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _dispatch(user_id: str, op: str, payload: dict, *, machine_id=None) -> dict:
        return {
            "status": "ok",
            "result": {"state": "window: Main (id=0)\n  [0] AXButton 'OK'"},
        }

    monkeypatch.setattr(cut, "dispatch_local_call", _dispatch)
    result = await _call(action="state", pid=42)
    assert "[0] AXButton 'OK'" in result


@pytest.mark.asyncio
async def test_state_preserves_window_metadata_and_screenshot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _dispatch(*args: Any, **kwargs: Any) -> dict:
        return {
            "result": {
                "pid": 42,
                "window": {"window_id": 0, "title": "编辑器", "bounds": [0, 0, 800, 600]},
                "element_count": 1,
                "truncated": False,
                "state": "window: 编辑器 (id=0)\n[0] AXButton 'OK'",
                "screenshot": {
                    "mime": "image/jpeg",
                    "width": 800,
                    "height": 600,
                    "data_b64": "abcd",
                },
            }
        }

    async def _upload(
        result: dict, base_url: str, *, private=False, private_user_id=None, private_session_id=None
    ) -> None:
        assert private is True
        assert private_user_id == "u1"
        assert private_session_id == "session-1"
        block = result["blocks"][0]
        assert block["base64"] == "abcd"
        assert block["mime_type"] == "image/jpeg"
        block.pop("base64")
        block["url"] = "/api/upload/file/cua-test.jpg"

    monkeypatch.setattr(cut, "upload_binary_blocks", _upload)
    monkeypatch.setattr(cut, "dispatch_local_call", _dispatch)
    result = json.loads(await _call(action="state", pid=42, include_screenshot=True))
    assert result["window"] == {"window_id": 0, "title": "编辑器", "bounds": [0, 0, 800, 600]}
    assert result["element_count"] == 1
    assert result["truncated"] is False
    assert result["screenshot"]["url"] == "/api/upload/file/cua-test.jpg"
    assert "data_b64" not in result["screenshot"]


@pytest.mark.asyncio
async def test_apps_preserves_structured_list(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _dispatch(*args: Any, **kwargs: Any) -> dict:
        return {"result": {"apps": [{"pid": 1, "name": "Notes", "active": True}]}}

    monkeypatch.setattr(cut, "dispatch_local_call", _dispatch)
    assert json.loads(await _call(action="apps")) == {
        "machine_id": "mac-staging-cua",
        "apps": [{"pid": 1, "name": "Notes", "active": True}],
    }


@pytest.mark.asyncio
async def test_structured_error_is_formatted(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _dispatch(user_id: str, op: str, payload: dict, *, machine_id=None) -> dict:
        return {"status": "ok", "result": {"error": "ax_not_trusted", "detail": "grant…"}}

    monkeypatch.setattr(cut, "dispatch_local_call", _dispatch)
    result = await _call(action="state", pid=42)
    assert result.startswith("ERROR ax_not_trusted")


@pytest.mark.asyncio
async def test_daemon_offline_appends_hint(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _dispatch(user_id: str, op: str, payload: dict, *, machine_id=None) -> dict:
        raise AppError(ErrorCode.DAEMON_OFFLINE)

    monkeypatch.setattr(cut, "dispatch_local_call", _dispatch)
    result = await _call(action="apps")
    assert result.startswith("ERROR dispatch_failed")
    assert "desktop app" in result


@pytest.mark.asyncio
async def test_app_error_detail_is_interpolated(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _dispatch(user_id: str, op: str, payload: dict, *, machine_id=None) -> dict:
        raise AppError(ErrorCode.SANDBOX_EXEC_FAILED, args={"detail": "cua backend crashed"})

    monkeypatch.setattr(cut, "dispatch_local_call", _dispatch)
    result = await _call(action="state", pid=42)
    assert result.startswith("ERROR dispatch_failed")
    assert "cua backend crashed" in result
    assert "{{" not in result


@pytest.mark.asyncio
async def test_element_index_becomes_target_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}

    async def _dispatch(user_id: str, op: str, payload: dict, *, machine_id=None) -> dict:
        captured.update(op=op, payload=payload)
        return {"status": "ok", "result": {"ok": True}}

    monkeypatch.setattr(cut, "dispatch_local_call", _dispatch)
    await _call(action="click", pid=7, index=3)
    assert captured["op"] == "cua_click"
    assert captured["payload"]["target"] == {"type": "element", "index": 3}
    assert captured["payload"]["pid"] == 7


@pytest.mark.asyncio
async def test_coordinate_target_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}

    async def _dispatch(user_id: str, op: str, payload: dict, *, machine_id=None) -> dict:
        captured.update(payload=payload)
        return {"status": "ok", "result": {"ok": True}}

    monkeypatch.setattr(cut, "dispatch_local_call", _dispatch)
    await _call(action="click", pid=7, x=12, y=34)
    assert captured["payload"]["target"] == {"type": "coordinate", "x": 12.0, "y": 34.0}


@pytest.mark.asyncio
async def test_apps_listing_format(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _dispatch(user_id: str, op: str, payload: dict, *, machine_id=None) -> dict:
        return {
            "status": "ok",
            "result": {"apps": [{"pid": 1, "name": "Notes", "active": True}]},
        }

    monkeypatch.setattr(cut, "dispatch_local_call", _dispatch)
    result = await _call(action="apps")
    assert json.loads(result)["apps"] == [{"pid": 1, "name": "Notes", "active": True}]


@pytest.mark.asyncio
async def test_launch_requires_url_or_app(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _dispatch(*args: Any, **kwargs: Any) -> dict:
        return {"status": "ok", "result": {"ok": True}}

    monkeypatch.setattr(cut, "dispatch_local_call", _dispatch)
    assert (await _call(action="launch")).startswith("ERROR invalid_arguments")


@pytest.mark.asyncio
async def test_launch_url_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}

    async def _dispatch(user_id: str, op: str, payload: dict, **kw: Any) -> dict:
        captured.update(op=op, payload=payload, kw=kw)
        return {"status": "ok", "result": {"ok": True, "kind": "url"}}

    monkeypatch.setattr(cut, "dispatch_local_call", _dispatch)
    result = await _call(action="launch", url="https://www.baidu.com")
    assert "ok" in result or "True" in result or result == "" or "url" in result
    assert captured["op"] == "cua_launch"
    assert captured["payload"]["url"] == "https://www.baidu.com"


@pytest.mark.asyncio
async def test_machine_id_forwarded_to_dispatch(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}

    async def _dispatch(user_id: str, op: str, payload: dict, *, machine_id=None) -> dict:
        captured.update(machine_id=machine_id)
        return {"status": "ok", "result": {"apps": []}}

    monkeypatch.setattr(cut, "dispatch_local_call", _dispatch)
    await _call(action="apps", machine_id="mac-staging-cua")
    assert captured["machine_id"] == "mac-staging-cua"


@pytest.mark.asyncio
async def test_launch_does_not_require_pid(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _dispatch(*args: Any, **kwargs: Any) -> dict:
        return {"status": "ok", "result": {"ok": True, "kind": "url"}}

    monkeypatch.setattr(cut, "dispatch_local_call", _dispatch)
    result = await _call(action="launch", url="https://example.com")
    assert not result.startswith("ERROR invalid_arguments")


@pytest.mark.asyncio
async def test_app_error_detail_is_interpolated_not_leaked(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """生产事故回归(2026-10-08):str(AppError) 拿到的是未插值模板,
    daemon 侧真实错误全被吞成 "Local sandbox execution failed: {{detail}}"。"""

    async def _dispatch(user_id: str, op: str, payload: dict, *, machine_id=None) -> dict:
        raise AppError(ErrorCode.SANDBOX_EXEC_FAILED, args={"detail": "pyperclip missing"})

    monkeypatch.setattr(cut, "dispatch_local_call", _dispatch)
    result = await _call(action="apps")
    assert result.startswith("ERROR dispatch_failed")
    assert "pyperclip missing" in result
    assert "{{detail}}" not in result


@pytest.mark.asyncio
async def test_activate_action_routes_to_cua_activate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    async def _dispatch(user_id: str, op: str, payload: dict, *, machine_id=None) -> dict:
        captured.update(op=op, payload=payload)
        return {"status": "ok", "result": {"ok": True, "pid": 7}}

    monkeypatch.setattr(cut, "dispatch_local_call", _dispatch)
    result = await _call(action="activate", pid=7, window_id=0)
    assert captured["op"] == "cua_activate"
    assert captured["payload"]["pid"] == 7
    assert captured["payload"]["window_id"] == 0
    assert "ok" in result


@pytest.mark.asyncio
async def test_element_action_name_reaches_daemon(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}

    async def _dispatch(user_id: str, op: str, payload: dict, *, machine_id=None) -> dict:
        captured.update(op=op, payload=payload)
        return {"result": {"ok": True}}

    monkeypatch.setattr(cut, "dispatch_local_call", _dispatch)
    await _call(action="action", pid=42, index=0, element_action="Press")
    assert captured["payload"]["action"] == "Press"


@pytest.mark.asyncio
async def test_large_tree_keeps_valid_json_and_screenshot_metadata() -> None:
    raw = await cut._format_result(
        {
            "state": "[0] AXTextField value='" + "a\\b中文" * 40_000,
            "element_count": 400,
            "truncated": False,
            "screenshot": {"url": "/api/upload/file/shot.jpg", "width": 800, "height": 600},
        }
    )
    assert len(raw) < 100_000
    result = json.loads(raw)
    assert result["truncated"] is True
    assert result["screenshot"]["url"] == "/api/upload/file/shot.jpg"
    assert result["state"].startswith("[0] AXTextField")
