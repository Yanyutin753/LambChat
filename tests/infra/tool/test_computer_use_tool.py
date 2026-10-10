"""computer_use 工具单测:动作校验、payload 构建、结果格式化与错误收敛。"""

from __future__ import annotations

import asyncio
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


async def test_automatic_selection_pins_registry_default_machine(monkeypatch):
    """自动档（未显式选机）：由注册表缺省解析（默认机→唯一在线→legacy）钉住
    目标机——默认机开箱即用，不再强制用户手动选中。"""

    class _Registry:
        def __init__(self, target):
            self._target = target

        async def resolve_target(self, user_id, machine_id=None):
            assert user_id == "u1"
            return self._target

    monkeypatch.setattr(cut, "SandboxClientRegistry", lambda: _Registry("default-mac"))
    assert await cut.resolve_computer_use_context("u1", {"sandbox": "local"}) == {
        "platform": "local",
        "machine_id": "default-mac",
    }


async def test_automatic_selection_without_online_machine_stays_unpinned(monkeypatch):
    """无任何在线机：钉不住目标（None），工具层按 machine_selection_required
    收敛——自动档解析不能凭空造出机器。"""

    class _Registry:
        async def resolve_target(self, user_id, machine_id=None):
            return None

    monkeypatch.setattr(cut, "SandboxClientRegistry", lambda: _Registry())
    assert await cut.resolve_computer_use_context("u1", {"sandbox": "local"}) == {
        "platform": "local",
        "machine_id": None,
    }


async def test_pinned_default_machine_flows_to_dispatch(monkeypatch):
    """自动档钉住的默认机进入 dispatch：与显式选机同一条确认链路。"""
    captured = {}

    async def dispatch(user_id, op, payload, *, machine_id=None):
        captured["machine_id"] = machine_id
        return {"result": {"ok": True}}

    async def lookup(user_id, machine_id=None):
        return "none"

    monkeypatch.setattr(cut, "_lookup_confirm_policy", lookup, raising=False)
    monkeypatch.setattr(cut, "dispatch_local_call", dispatch)
    result = await _call(action="apps", runtime=_runtime(machine="default-mac"))
    assert json.loads(result)["ok"] is True
    assert captured["machine_id"] == "default-mac"


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
    "runtime",
    [_runtime(machine=None), _runtime(platform="cloud", machine=None), SimpleNamespace(config={})],
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


async def test_cloud_code_sandbox_uses_only_explicit_cua_machine(monkeypatch):
    async def dispatch(user_id, op, payload, *, machine_id=None):
        assert user_id == "u1" and machine_id == "selected-desktop"
        assert payload["session_id"] == "session-1"
        return {"result": {"ok": True}}

    monkeypatch.setattr(cut, "dispatch_local_call", dispatch)
    result = await _call(
        action="apps", runtime=_runtime(platform="cloud", machine="selected-desktop")
    )
    assert json.loads(result)["machine_id"] == "selected-desktop"


async def test_screenshot_upload_receives_runtime_origin(monkeypatch):
    async def upload(result, base_url, **kwargs):
        result["blocks"][0]["url"] = base_url + "/api/upload/file/cua_screenshots/u/s/a.jpg"

    monkeypatch.setattr(cut, "upload_binary_blocks", upload)
    runtime = _runtime()
    runtime.config["configurable"]["base_url"] = "https://app.example"
    result = json.loads(await cut._format_result({"screenshot": {"data_b64": "abcd"}}, runtime))
    assert (
        result["screenshot"]["url"]
        == "https://app.example/api/upload/file/cua_screenshots/u/s/a.jpg"
    )


def test_cua_workflow_guides_agent_to_external_file_picker_process():
    assert "portal" in cut.computer_use.description
    assert "apps" in cut.computer_use.description


def test_cua_workflow_distinguishes_desktop_files_from_agent_workspace():
    assert "desktop files" in cut.computer_use.description
    assert "virtual filesystem" in cut.computer_use.description


def test_cua_workflow_checks_active_document_in_tabbed_office_editors():
    assert "active document tab" in cut.computer_use.description
    assert "pid alone" in cut.computer_use.description


def test_cua_workflow_explains_screenshots_to_vision_enabled_models():
    assert "vision-enabled models" in cut.computer_use.description
    assert "base64 for the human/UI" not in cut.computer_use.description


def test_cua_workflow_uses_exact_spreadsheet_cell_addresses():
    assert "Name Box" in cut.computer_use.description
    assert "cell addresses" in cut.computer_use.description


def test_cua_workflow_verifies_formatting_before_repeating_a_toggle():
    assert "Formatting shortcuts toggle" in cut.computer_use.description
    assert "current value or format dialog" in cut.computer_use.description
    assert "do not infer success from font appearance alone" in cut.computer_use.description


def test_cua_workflow_discovers_office_dialog_process_before_observing():
    assert "Office dialogs can run in a different process" in cut.computer_use.description
    assert "active dialog's pid" in cut.computer_use.description


def test_cua_schema_requires_explicit_app_target_for_coordinate_actions():
    description = cut.computer_use.args_schema.model_fields["pid"].description
    assert "Required unless name is supplied" in description
    assert "Coordinate clicks also require pid or name" in cut.computer_use.description


async def test_cua_parallel_calls_preserve_order_before_confirmation_lookup(monkeypatch):
    first_lookup = asyncio.Event()
    release_first = asyncio.Event()
    seen = []
    lookups = 0

    async def lookup(user_id, machine_id=None):
        nonlocal lookups
        lookups += 1
        if lookups == 1:
            first_lookup.set()
            await release_first.wait()
        return "none"

    async def dispatch(user_id, op, payload, *, machine_id=None):
        seen.append(payload["text"])
        return {"result": {"ok": True}}

    monkeypatch.setattr(cut, "_lookup_confirm_policy", lookup)
    monkeypatch.setattr(cut, "dispatch_local_call", dispatch)
    first = asyncio.create_task(
        cut.computer_use.coroutine(action="type", pid=123, text="first", runtime=_runtime())
    )
    await first_lookup.wait()
    second = asyncio.create_task(
        cut.computer_use.coroutine(action="key", pid=123, text="Return", runtime=_runtime())
    )
    try:
        await asyncio.sleep(0)
        assert seen == [], "later GUI input overtook the blocked first operation"
    finally:
        release_first.set()
        await asyncio.gather(first, second)
    assert seen == ["first", "Return"]


async def test_cua_serialization_does_not_block_another_desktop(monkeypatch):
    started = asyncio.Event()
    release = asyncio.Event()

    async def dispatch(user_id, op, payload, *, machine_id=None):
        if machine_id == "busy-desktop":
            started.set()
            await release.wait()
        return {"result": {"machine": machine_id}}

    monkeypatch.setattr(cut, "dispatch_local_call", dispatch)
    busy = asyncio.create_task(_call(action="apps", runtime=_runtime(machine="busy-desktop")))
    await started.wait()
    try:
        other = await asyncio.wait_for(
            _call(action="apps", runtime=_runtime(machine="other-desktop")), timeout=1
        )
        assert json.loads(other)["machine"] == "other-desktop"
    finally:
        release.set()
        await busy


async def test_cua_cancellation_releases_desktop_queue(monkeypatch):
    started = asyncio.Event()

    async def dispatch(user_id, op, payload, *, machine_id=None):
        if op == "cua_type":
            started.set()
            await asyncio.Event().wait()
        return {"result": {"ok": True}}

    monkeypatch.setattr(cut, "dispatch_local_call", dispatch)
    pending = asyncio.create_task(_call(action="type", pid=123, text="test"))
    await started.wait()
    pending.cancel()
    with pytest.raises(asyncio.CancelledError):
        await pending
    result = await asyncio.wait_for(_call(action="apps"), timeout=1)
    assert json.loads(result)["ok"] is True


def test_scroll_guidance_targets_content_and_verifies_movement():
    assert "nested scroll" in cut.computer_use.description
    assert "0.1" in cut.computer_use.description
    assert "verify movement" in cut.computer_use.description
    assert "wheel notches" in cut.computer_use.args_schema.model_fields["scroll_amount"].description


def test_nested_scroll_guidance_avoids_boundary_probe_chaining():
    assert "scroll chaining" in cut.computer_use.description
    assert "do not probe" in cut.computer_use.description
    assert "parent" in cut.computer_use.description


def test_observation_guidance_stops_when_current_evidence_meets_the_goal():
    assert (
        "If the current tree and screenshot demonstrate the requested outcome"
        in cut.computer_use.description
    )
    assert "finish without more input or identical observations" in cut.computer_use.description


def test_state_guidance_allows_subtree_and_avoids_reobserving_read_only_calls():
    assert "state(index=...)" in cut.computer_use.description
    assert "Read-only status/apps/windows/state calls" in cut.computer_use.description
    assert "no new evidence" in cut.computer_use.description
