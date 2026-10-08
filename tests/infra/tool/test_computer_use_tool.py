"""computer_use 工具单测:动作校验、payload 构建、结果格式化与错误收敛。"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from src.infra.tool import computer_use_tool as cut
from src.kernel.errors import AppError, ErrorCode


def _runtime(user_id: str = "u1") -> Any:
    return SimpleNamespace(config={"configurable": {"context": SimpleNamespace(user_id=user_id)}})


async def _call(**kwargs: Any) -> str:
    merged = {"runtime": _runtime()}
    merged.update(kwargs)
    return await cut.computer_use.ainvoke(merged)


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
    assert "pid=1 Notes [active]" in result


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
