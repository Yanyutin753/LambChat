"""cua_ops 单元测试:用假后端驱动平台无关语义(索引/缓存/预算/错误收敛)。

CI(Linux)上不依赖任何平台库——cua_backend 被 monkeypatch 为假实现。
"""

from __future__ import annotations

from typing import Any

import pytest

from lambchat_sandbox import cua_backend, cua_ops


class _FakeElement:
    def __init__(self, kind: str, title: str = "", children: list | None = None):
        self.kind = kind
        self.title = title
        self.children = children or []


def test_snapshot_pins_its_window_when_another_window_was_observed(fake_backend, monkeypatch):
    original = fake_backend.pick_window

    def pick(pid, window_id):
        element, window = original(pid, None)
        return element, {**window, "window_id": window_id or 0}

    monkeypatch.setattr(fake_backend, "pick_window", pick)
    first = cua_ops.handle_cua_op("cua_state", {"pid": 4242, "window_id": 0})
    cua_ops.handle_cua_op("cua_state", {"pid": 4242, "window_id": 1})
    result = cua_ops.handle_cua_op(
        "cua_click",
        {
            "pid": 4242,
            "snapshot_id": first["snapshot_id"],
            "target": {"type": "element", "index": 1},
        },
    )
    assert "error" not in result
    assert fake_backend.performed


class _FakeBackend:
    platform_name = "fake"

    def __init__(self):
        self.performed: list[tuple[Any, str]] = []
        self.set_values: list[tuple[Any, str]] = []
        self.focused: list[Any] = []
        self.activated: list[tuple[int, int | None]] = []
        self.set_value_error: Exception | None = None
        self.window = _FakeElement(
            "AXWindow",
            "Main",
            [_FakeElement("AXButton", "确定"), _FakeElement("AXTextField", "搜索")],
        )

    def click_point(self, x, y, button="left", *, count=1):
        return {}

    def type_text(self, text, window):
        return {}

    def press_chord(self, keys, modifiers, window):
        return {}

    def scroll_point(self, x, y, direction, amount):
        return {}

    def launch(self, app, args):
        return {}

    def ax_trusted(self) -> bool:
        return True

    def frontmost_pid(self) -> int | None:
        return 4242

    def list_apps(self) -> list[dict[str, Any]]:
        return [{"pid": 4242, "name": "Notes"}, {"pid": 100, "name": "Finder"}]

    def windows(self, pid: int) -> list[dict[str, Any]]:
        return [
            {
                "window_id": 0,
                "title": "Main",
                "subrole": "AXStandardWindow",
                "main": True,
                "focused": True,
                "bounds": [10.0, 20.0, 800.0, 600.0],
                "handle": self.window,
            }
        ]

    def pick_window(self, pid: int, window_id: int | None) -> tuple[Any, dict[str, Any]]:
        assert pid == 4242
        if window_id is not None and window_id != 0:
            raise KeyError("window index out of range")
        return self.window, {
            "window_id": 0,
            "title": "Main",
            "bounds": [10.0, 20.0, 800.0, 600.0],
            "focused": True,
        }

    def children(self, element: Any) -> list[Any]:
        return element.children

    def row_of(self, element: Any) -> dict[str, Any]:
        return {
            "kind": element.kind,
            "title": element.title,
            "value": None,
            "actions": ["AXPress"],
            "bounds": [1.0, 2.0, 100.0, 40.0],
        }

    def perform(self, element: Any, action: str) -> None:
        self.performed.append((element, action))

    def set_value(self, element: Any, text: str) -> None:
        if self.set_value_error is not None:
            raise self.set_value_error
        self.set_values.append((element, text))

    def set_focus(self, element: Any) -> None:
        self.focused.append(element)

    def activate_window(self, pid: int, window_id: int | None) -> None:
        self.activated.append((pid, window_id))


@pytest.fixture
def fake_backend(monkeypatch: pytest.MonkeyPatch) -> _FakeBackend:
    fake = _FakeBackend()
    monkeypatch.setattr(cua_backend, "_BACKEND", fake)
    monkeypatch.setattr(cua_backend, "_BACKEND_ERROR", None)
    monkeypatch.setattr(cua_backend, "backend_platform", lambda: "fake")
    cua_ops._OBSERVATIONS.clear()
    return fake


def test_apps_marks_frontmost(fake_backend: _FakeBackend) -> None:
    result = cua_ops.handle_cua_op("cua_apps", {})
    by_name = {row["name"]: row for row in result["apps"]}
    assert by_name["Notes"]["active"] is True
    assert by_name["Finder"]["active"] is False


def test_snapshot_id_rejects_index_from_replaced_observation(fake_backend):
    first = cua_ops.handle_cua_op("cua_state", {"pid": 4242})
    cua_ops.handle_cua_op("cua_state", {"pid": 4242})
    result = cua_ops.handle_cua_op(
        "cua_click",
        {
            "pid": 4242,
            "snapshot_id": first["snapshot_id"],
            "target": {"type": "element", "index": 1},
        },
    )
    assert result["error"] == "stale_state"
    assert not fake_backend.performed


def test_element_double_click_does_not_degrade_to_single_semantic_press(fake_backend, monkeypatch):
    cua_ops.handle_cua_op("cua_state", {"pid": 4242})
    calls = []
    monkeypatch.setattr(
        fake_backend,
        "click_point",
        lambda *args, **kwargs: calls.append((args, kwargs)) or {},
        raising=False,
    )
    result = cua_ops.handle_cua_op(
        "cua_click",
        {
            "pid": 4242,
            "target": {"type": "element", "index": 1},
            "click_count": 2,
        },
    )
    assert result["ok"]
    assert not fake_backend.performed
    assert calls == [((51.0, 22.0, "left"), {"count": 2})]


def test_driver_input_error_is_not_replayed_as_keyboard_input(fake_backend, monkeypatch):
    cua_ops.handle_cua_op("cua_state", {"pid": 4242})

    def rejected(*args):
        raise cua_ops.CuaOpError("stale_state", "delivery uncertain; observe")

    monkeypatch.setattr(fake_backend, "set_value", rejected)
    monkeypatch.setattr(
        cua_ops, "_type_text", lambda text, *args: pytest.fail("unsafe input replay")
    )
    result = cua_ops.handle_cua_op(
        "cua_type",
        {
            "pid": 4242,
            "target": {"type": "element", "index": 2},
            "text": "test",
        },
    )
    assert result["error"] == "stale_state"


def test_screenshot_coordinates_are_scaled_by_daemon(fake_backend, monkeypatch):
    monkeypatch.setattr(
        cua_ops, "_capture", lambda bounds, window=None: {"width": 400, "height": 300}
    )
    state = cua_ops.handle_cua_op("cua_state", {"pid": 4242, "include_screenshot": True})
    calls = []
    monkeypatch.setattr(
        fake_backend, "click_point", lambda *args, **kwargs: calls.append(args) or {}, raising=False
    )
    result = cua_ops.handle_cua_op(
        "cua_click",
        {
            "pid": 4242,
            "snapshot_id": state.get("snapshot_id"),
            "coordinate_space": "screenshot",
            "target": {"x": 200, "y": 150},
        },
    )
    assert result["ok"]
    assert calls == [(410.0, 320.0, "left")]


def test_driver_observation_error_is_not_an_empty_success(fake_backend, monkeypatch):
    def fail(element):
        raise cua_ops.CuaOpError("stale_state", "window ownership changed")

    monkeypatch.setattr(fake_backend, "row_of", fail)
    result = cua_ops.handle_cua_op("cua_state", {"pid": 4242})
    assert result["error"] == "stale_state"


@pytest.mark.parametrize("clicks", [1, 2, 3])
def test_native_coordinate_click_preserves_click_count(fake_backend, monkeypatch, clicks):
    calls = []
    monkeypatch.setattr(
        fake_backend,
        "click_point",
        lambda *args, **kwargs: calls.append((args, kwargs)) or {},
        raising=False,
    )
    result = cua_ops.handle_cua_op(
        "cua_click",
        {"pid": 4242, "target": {"x": 30, "y": 40}, "click_count": clicks},
    )
    assert result["ok"]
    assert calls == [((30.0, 40.0, "left"), {"count": clicks})]


def test_state_walks_tree_and_stores_indices(fake_backend: _FakeBackend) -> None:
    result = cua_ops.handle_cua_op("cua_state", {"pid": 4242})
    assert result["element_count"] == 3  # 窗口 + 按钮 + 输入框
    assert "[0] AXWindow 'Main'" in result["state"]
    assert "[1] AXButton '确定'" in result["state"]
    observed = cua_ops._OBSERVATIONS[(None, 4242, 0)]
    assert len(observed.elements) == 3


def test_state_can_observe_a_subtree_and_replaces_its_indices(fake_backend):
    cua_ops.handle_cua_op("cua_state", {"pid": 4242})
    result = cua_ops.handle_cua_op(
        "cua_state", {"pid": 4242, "target": {"type": "element", "index": 1}}
    )
    assert result["element_count"] == 1
    assert "[0] AXButton '确定'" in result["state"]
    assert result["subtree"] is True
    assert result["window"]["title"] == "Main"
    cua_ops.handle_cua_op("cua_click", {"pid": 4242, "target": {"type": "element", "index": 0}})
    assert fake_backend.performed[-1][0] is fake_backend.window.children[0]


@pytest.mark.parametrize("index,error", [(0, "stale_state"), (999, "element_unavailable")])
def test_subtree_observation_rejects_missing_or_invalid_prior_index(fake_backend, index, error):
    if index:
        cua_ops.handle_cua_op("cua_state", {"pid": 4242})
    result = cua_ops.handle_cua_op(
        "cua_state", {"pid": 4242, "target": {"type": "element", "index": index}}
    )
    assert result["error"] == error


def test_click_element_uses_latest_observation(fake_backend: _FakeBackend) -> None:
    cua_ops.handle_cua_op("cua_state", {"pid": 4242})
    result = cua_ops.handle_cua_op(
        "cua_click", {"pid": 4242, "target": {"type": "element", "index": 1}}
    )
    assert result == {"ok": True, "strategy": "a11y", "action": "click"}
    element, action = fake_backend.performed[0]
    assert element.kind == "AXButton"
    assert action == "click"


def test_acting_without_observation_reports_stale_state(fake_backend: _FakeBackend) -> None:
    result = cua_ops.handle_cua_op(
        "cua_click", {"pid": 4242, "target": {"type": "element", "index": 0}}
    )
    assert result["error"] == "stale_state"


def test_out_of_range_index_fails_closed(fake_backend: _FakeBackend) -> None:
    cua_ops.handle_cua_op("cua_state", {"pid": 4242})
    result = cua_ops.handle_cua_op(
        "cua_click", {"pid": 4242, "target": {"type": "element", "index": 99}}
    )
    assert result["error"] == "element_unavailable"


def test_set_value_passes_text_to_backend(fake_backend: _FakeBackend) -> None:
    cua_ops.handle_cua_op("cua_state", {"pid": 4242})
    result = cua_ops.handle_cua_op(
        "cua_set_value", {"pid": 4242, "target": {"type": "element", "index": 2}, "value": "hello"}
    )
    assert result == {"ok": True}
    assert fake_backend.set_values[0][1] == "hello"


def test_unknown_app_name_reports_not_found(fake_backend: _FakeBackend) -> None:
    cua_ops.handle_cua_op("cua_state", {"pid": 4242})
    result = cua_ops.handle_cua_op("cua_state", {"name": "不存在的应用"})
    assert result["error"] == "app_not_found"


def test_truncation_when_tree_exceeds_budget(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _FakeBackend()
    fake.window = _FakeElement(
        "AXWindow", "Big", [_FakeElement("AXStaticText", f"t{i}") for i in range(500)]
    )
    monkeypatch.setattr(cua_backend, "_BACKEND", fake)
    monkeypatch.setattr(cua_backend, "_BACKEND_ERROR", None)
    cua_ops._OBSERVATIONS.clear()
    result = cua_ops.handle_cua_op("cua_state", {"pid": 4242})
    assert result["truncated"] is True
    assert result["element_count"] == cua_ops.STATE_MAX_ELEMENTS


def test_untrusted_ax_converges_to_structured_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _Denied(_FakeBackend):
        def ax_trusted(self) -> bool:
            return False

    monkeypatch.setattr(cua_backend, "_BACKEND", _Denied())
    monkeypatch.setattr(cua_backend, "_BACKEND_ERROR", None)
    result = cua_ops.handle_cua_op("cua_state", {"pid": 4242})
    assert result["error"] == "ax_not_trusted"


def test_status_without_backend_reports_unsupported(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(cua_backend, "_BACKEND", None)
    monkeypatch.setattr(cua_backend, "_BACKEND_ERROR", "backend_import_failed:nope")
    result = cua_ops.handle_cua_op("cua_status", {})
    assert result["platform"] == "unsupported"
    assert result["ready"] is False


def test_invalid_arguments_for_non_status_actions(fake_backend: _FakeBackend) -> None:
    result = cua_ops.handle_cua_op("cua_state", {})
    assert result["error"] == "invalid_arguments"


# ---------------------------------------------------------------------------
# 2026-10-08 生产质量回修:type 免前台路径 / activate / 异常结构化
# ---------------------------------------------------------------------------


def test_type_with_index_writes_value_without_foreground(
    fake_backend: _FakeBackend, monkeypatch: pytest.MonkeyPatch
) -> None:
    """带 index 的 type 走 focus+set_value 免前台——后台窗口也能输入,
    不再一律 foreground_required(生产实测 Windows Edge 地址框即此坑)。"""
    # 前台是别的应用,元素路径仍必须成功
    monkeypatch.setattr(fake_backend, "frontmost_pid", lambda: 9999)
    cua_ops.handle_cua_op("cua_state", {"pid": 4242})
    result = cua_ops.handle_cua_op("cua_type", {"pid": 4242, "index": 2, "text": "今日新闻"})
    assert result == {"ok": True, "strategy": "a11y", "method": "set_value"}
    assert fake_backend.set_values[0][1] == "今日新闻"
    assert fake_backend.focused  # 先聚焦过元素


def test_type_without_index_still_requires_foreground(
    fake_backend: _FakeBackend, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(fake_backend, "frontmost_pid", lambda: 9999)
    result = cua_ops.handle_cua_op("cua_type", {"pid": 4242, "text": "hello"})
    assert result["error"] == "foreground_required"


def test_type_index_unsettable_element_hints_activate(
    fake_backend: _FakeBackend, monkeypatch: pytest.MonkeyPatch
) -> None:
    """元素不可直写且不在前台:报 foreground_required 并指路 activate。"""
    monkeypatch.setattr(fake_backend, "frontmost_pid", lambda: 9999)
    fake_backend.set_value_error = KeyError("not settable")
    cua_ops.handle_cua_op("cua_state", {"pid": 4242})
    result = cua_ops.handle_cua_op("cua_type", {"pid": 4242, "index": 1, "text": "x"})
    assert result["error"] == "foreground_required"
    assert "activate" in result["detail"]


def test_activate_routes_to_backend(fake_backend: _FakeBackend) -> None:
    result = cua_ops.handle_cua_op("cua_activate", {"pid": 4242, "window_id": 0})
    assert result == {"ok": True, "pid": 4242}
    assert fake_backend.activated == [(4242, 0)]


def test_unexpected_exception_converges_structured(
    fake_backend: _FakeBackend, monkeypatch: pytest.MonkeyPatch
) -> None:
    """COMError 等三方异常不再裸穿 daemon 层(生产 dispatch_failed 主因)。
    在模型可读层收敛为 op_failed,错误类型与原文都在 detail 里。"""

    def _boom(payload: dict) -> dict:
        raise RuntimeError("COMError: element gone")

    monkeypatch.setitem(cua_ops._CUA_HANDLERS, "cua_apps", _boom)
    result = cua_ops.handle_cua_op("cua_apps", {})
    assert result["error"] == "op_failed"
    assert "RuntimeError" in result["detail"]
    assert "COMError" in result["detail"]


def test_cua_activate_in_ops_registry() -> None:
    assert "cua_activate" in cua_ops.CUA_OPS
    assert "cua_activate" in cua_ops._CUA_HANDLERS


# ---------------------------------------------------------------------------
# 2026-10-08 xiaoxin 真机回修:单键原生合成 / launch 裸名解析
# ---------------------------------------------------------------------------


def test_failed_native_key_is_not_replayed_through_another_input_backend(fake_backend, monkeypatch):
    cua_ops.handle_cua_op("cua_state", {"pid": 4242})
    calls = []

    def native(keys, modifiers, window):
        calls.extend(keys)
        raise RuntimeError("readback failed after delivery")

    monkeypatch.setattr(fake_backend, "press_chord", native, raising=False)
    result = cua_ops.handle_cua_op("cua_key", {"pid": 4242, "text": "return"})
    assert result["error"] == "action_failed"
    assert result["disposition"]["retry"] == "unsafe"
    assert calls == ["enter"]


def test_failed_value_write_is_not_replayed_as_typing(fake_backend, monkeypatch):
    cua_ops.handle_cua_op("cua_state", {"pid": 4242})
    fake_backend.set_value_error = RuntimeError("readback failed after writing")
    monkeypatch.setattr(
        cua_ops, "_type_text", lambda text, *args: pytest.fail("must not duplicate input")
    )
    result = cua_ops.handle_cua_op(
        "cua_type", {"pid": 4242, "target": {"type": "element", "index": 0}, "text": "中文"}
    )
    assert result["error"] == "action_failed"
    assert result["disposition"]["retry"] == "unsafe"


def test_unknown_foreground_refuses_keyboard_injection(
    fake_backend: _FakeBackend, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(fake_backend, "frontmost_pid", lambda: None)
    result = cua_ops.handle_cua_op("cua_key", {"pid": 4242, "text": "return"})
    assert result["error"] == "foreground_required"


def test_screenshot_denied_preserves_the_accessibility_tree(
    fake_backend: _FakeBackend, monkeypatch: pytest.MonkeyPatch
) -> None:
    def denied(_bounds, window=None):
        raise cua_ops.CuaOpError("screen_recording_denied", "grant permission")

    monkeypatch.setattr(cua_ops, "_capture", denied)
    result = cua_ops.handle_cua_op("cua_state", {"pid": 4242, "include_screenshot": True})
    assert result["element_count"] == 3
    assert "AXButton" in result["state"]
    assert result["screenshot"] == {
        "error": "screen_recording_denied",
        "detail": "grant permission",
    }


def test_type_reads_index_from_tool_target_shape(fake_backend: _FakeBackend) -> None:
    """工具层把 index 放在 target.index(与 click/set_value 同形);daemon
    只读顶层会让元素输入路径在真实链路上静默失效。"""
    cua_ops.handle_cua_op("cua_state", {"pid": 4242})
    result = cua_ops.handle_cua_op(
        "cua_type",
        {"pid": 4242, "target": {"type": "element", "index": 2}, "text": "hi"},
    )
    assert result["method"] == "set_value"
    assert fake_backend.set_values[0][1] == "hi"


def test_failed_screenshot_probe_is_not_reported_as_ready(fake_backend, monkeypatch):
    def failed(bounds):
        raise cua_ops.CuaOpError("screenshot_failed", "desktop unavailable")

    monkeypatch.setattr(cua_ops, "_capture", failed)
    result = cua_ops.handle_cua_op("cua_status", {"probe_screen": True})
    assert result["ready"] is False
    assert "desktop unavailable" in result["message"]


def test_element_scroll_prefers_native_accessibility_without_foreground(fake_backend, monkeypatch):
    cua_ops.handle_cua_op("cua_state", {"pid": 4242})
    calls = []
    monkeypatch.setattr(fake_backend, "frontmost_pid", lambda: None)
    monkeypatch.setattr(
        fake_backend,
        "scroll_element",
        lambda *args, **kwargs: calls.append(args) or {},
        raising=False,
    )
    result = cua_ops.handle_cua_op(
        "cua_scroll",
        {
            "pid": 4242,
            "target": {"type": "element", "index": 1},
            "scroll_direction": "down",
            "scroll_amount": 2,
        },
    )
    assert result["ok"] and result["strategy"] == "a11y"
    assert calls[0][1:] == ("down", 2)


@pytest.mark.parametrize(
    "bounds",
    [
        None,
        [],
        [0, 0, 0, 100],
        [0, 0, -5, 100],
        [0, 0, float("nan"), 100],
        [0, float("inf"), 100, 100],
        ["0", 0, 100, 100],
    ],
)
def test_capture_rejects_invalid_window_bounds_before_reading_pixels(
    fake_backend, monkeypatch, bounds
):
    def capture(_bounds, window=None):
        pytest.fail("invalid bounds must never capture desktop pixels")

    monkeypatch.setattr(fake_backend, "screenshot", capture, raising=False)
    with pytest.raises(cua_ops.CuaOpError, match="screenshot_failed"):
        cua_ops._capture(bounds)


def test_background_state_keeps_tree_but_refuses_screen_region(fake_backend, monkeypatch):
    monkeypatch.setattr(fake_backend, "frontmost_pid", lambda: 100)
    monkeypatch.setattr(
        cua_ops, "_capture", lambda bounds, window=None: pytest.fail("background pixels captured")
    )
    result = cua_ops.handle_cua_op("cua_state", {"pid": 4242, "include_screenshot": True})
    assert "AXButton" in result["state"]
    assert result["screenshot"]["error"] == "foreground_required"
    assert result["foreground_pid"] == 100


def test_state_preserves_observation_when_foreground_pid_is_unavailable(fake_backend, monkeypatch):
    def unavailable():
        raise RuntimeError("desktop unavailable")

    monkeypatch.setattr(fake_backend, "frontmost_pid", unavailable)
    result = cua_ops.handle_cua_op("cua_state", {"pid": 4242})
    assert "AXButton" in result["state"]
    assert "foreground_pid" not in result


@pytest.mark.parametrize("window_id", [None, 0])
def test_element_indices_resolve_only_the_same_conversation(fake_backend, window_id):
    cua_ops.handle_cua_op("cua_state", {"pid": 4242, "session_id": "chat-a"})
    first = fake_backend.window.children[0]
    fake_backend.window = _FakeElement("AXWindow", "Other", [_FakeElement("AXButton", "Delete")])
    cua_ops.handle_cua_op("cua_state", {"pid": 4242, "session_id": "chat-b"})
    result = cua_ops.handle_cua_op(
        "cua_click",
        {
            "pid": 4242,
            "session_id": "chat-a",
            "window_id": window_id,
            "target": {"type": "element", "index": 1},
        },
    )
    assert result["ok"] is True
    assert fake_backend.performed == [(first, "click")]


@pytest.mark.parametrize(
    "observed_session,action_session", [(None, "chat-a"), ("chat-a", None), ("chat-a", "chat-b")]
)
def test_other_conversation_or_legacy_observation_cannot_authorize_an_element(
    fake_backend, observed_session, action_session
):
    cua_ops.handle_cua_op("cua_state", {"pid": 4242, "session_id": observed_session})
    result = cua_ops.handle_cua_op(
        "cua_click",
        {
            "pid": 4242,
            "session_id": action_session,
            "target": {"type": "element", "index": 1},
        },
    )
    assert result["error"] == "stale_state"
    assert fake_backend.performed == []


def test_conversation_observation_still_expires(fake_backend, monkeypatch):
    clock = [0.0]
    monkeypatch.setattr(cua_ops.time, "monotonic", lambda: clock[0])
    cua_ops.handle_cua_op("cua_state", {"pid": 4242, "session_id": "chat-a"})
    clock[0] = cua_ops.ELEMENT_CACHE_TTL + 1
    result = cua_ops.handle_cua_op(
        "cua_click",
        {
            "pid": 4242,
            "session_id": "chat-a",
            "target": {"type": "element", "index": 1},
        },
    )
    assert result["error"] == "stale_state"
    assert fake_backend.performed == []


def test_concurrent_daemon_threads_keep_conversation_indices_separate(fake_backend, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier, local

    thread = local()
    observed = Barrier(2)
    monkeypatch.setattr(
        fake_backend,
        "pick_window",
        lambda pid, wid: (
            thread.window,
            {"window_id": 0, "title": "Main", "bounds": [0, 0, 100, 100]},
        ),
    )

    monkeypatch.setattr(
        fake_backend, "perform", lambda element, action: setattr(thread, "clicked", element)
    )

    def act(session):
        button = _FakeElement("AXButton", session)
        thread.window = _FakeElement("AXWindow", "Main", [button])
        cua_ops.handle_cua_op("cua_state", {"pid": 4242, "session_id": session})
        observed.wait(timeout=5)
        result = cua_ops.handle_cua_op(
            "cua_click",
            {"pid": 4242, "session_id": session, "target": {"type": "element", "index": 1}},
        )
        return result, button, thread.clicked

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(act, ["chat-a", "chat-b"]))
    assert all(result["ok"] and clicked is button for result, button, clicked in results)


@pytest.mark.parametrize(
    "active",
    [
        {"window_id": 1, "bounds": [10.0, 20.0, 800.0, 600.0], "focused": True},
        {"window_id": 0, "bounds": [100.0, 200.0, 800.0, 600.0], "focused": True},
        {"bounds": [10.0, 20.0, 800.0, 600.0], "focused": True},
        None,
    ],
)
def test_same_app_other_or_unknown_active_window_refuses_screenshot(
    fake_backend, monkeypatch, active
):
    requested = {"window_id": 0, "title": "Main", "bounds": [10.0, 20.0, 800.0, 600.0]}

    def pick(pid, window_id):
        if window_id == 0:
            return fake_backend.window, requested
        if active is None:
            raise RuntimeError("cannot determine active window")
        return fake_backend.window, active

    monkeypatch.setattr(fake_backend, "pick_window", pick)
    monkeypatch.setattr(
        cua_ops, "_capture", lambda bounds, window=None: pytest.fail("wrong window pixels captured")
    )
    result = cua_ops.handle_cua_op(
        "cua_state",
        {
            "pid": 4242,
            "window_id": 0,
            "include_screenshot": True,
        },
    )
    assert "AXButton" in result["state"]
    assert result["screenshot"]["error"] == "foreground_required"


def test_same_app_active_window_allows_target_region_capture(fake_backend, monkeypatch):
    captures = []
    monkeypatch.setattr(
        cua_ops,
        "_capture",
        lambda bounds, window=None: captures.append(bounds) or {"mime": "image/jpeg"},
    )
    result = cua_ops.handle_cua_op(
        "cua_state",
        {
            "pid": 4242,
            "window_id": 0,
            "include_screenshot": True,
        },
    )
    assert result["screenshot"] == {"mime": "image/jpeg"}
    assert captures == [[10.0, 20.0, 800.0, 600.0]]


@pytest.mark.parametrize("focused", [False, None])
def test_unknown_or_unfocused_window_never_captures_pixels(fake_backend, monkeypatch, focused):
    info = {"window_id": 0, "title": "Main", "bounds": [0, 0, 100, 100], "focused": focused}
    monkeypatch.setattr(fake_backend, "pick_window", lambda pid, wid: (fake_backend.window, info))
    monkeypatch.setattr(
        cua_ops, "_capture", lambda bounds, window=None: pytest.fail("unfocused pixels captured")
    )
    result = cua_ops.handle_cua_op("cua_state", {"pid": 4242, "include_screenshot": True})
    assert result["screenshot"]["error"] == "foreground_required"
    assert "AXButton" in result["state"]


def test_state_preserves_full_text_and_omits_duplicate_value():
    title = "题目内容" * 80 + "最终区别"
    value = "回答内容" * 80 + "末尾答案"
    rows = [
        {"kind": "text", "title": title, "value": title, "depth": 0},
        {"kind": "textbox", "title": "回答", "value": value, "depth": 1},
        {"kind": "checkbox", "title": "选项", "value": False, "depth": 1},
    ]
    state = cua_ops._render_tree(rows, {"window_id": 1}, False)
    assert state.count(title) == 1
    assert value in state
    assert "[1] textbox '回答' value=" in state
    assert "value='False'" in state


def test_state_omits_empty_layout_nodes_without_renumbering_controls():
    rows = [
        {"kind": "frame", "title": "Calc", "depth": 0},
        {"kind": "filler", "depth": 1},
        {"kind": "panel", "title": "Font Name", "actions": ["press"], "depth": 2},
        {"kind": "panel", "depth": 2},
        {"kind": "text", "value": "中文测试", "depth": 3},
        {"kind": "Pane", "depth": 1},
        {"kind": "Window", "depth": 2},
        {"kind": "Pane", "actions": ["Invoke"], "depth": 2},
    ]
    state = cua_ops._render_tree(rows, {"title": "Calc", "window_id": 0}, False)
    assert "[1] filler" not in state
    assert "[3] panel" not in state
    assert "[2] panel 'Font Name' actions=press" in state
    assert "[4] text value='中文测试'" in state
    assert "[5] Pane" not in state
    assert "[6] Window" not in state
    assert "[7] Pane actions=Invoke" in state


@pytest.mark.parametrize("foreground", [True, False])
def test_click_unactionable_cell_falls_back_only_in_foreground(
    fake_backend, monkeypatch, foreground
):
    cua_ops.handle_cua_op("cua_state", {"pid": 4242})
    fake_backend.frontmost_pid = lambda: 4242 if foreground else 202

    def unsupported(*args):
        raise KeyError("no actions")

    monkeypatch.setattr(fake_backend, "perform", unsupported)
    clicks = []
    fake_backend.click_point = lambda x, y, button, **kwargs: clicks.append((x, y, button)) or {}
    payload = {"pid": 4242, "target": {"type": "element", "index": 1}}
    if foreground:
        result = cua_ops.handle_cua_op("cua_click", payload)
        assert result["ok"] is True
        assert clicks == [(51.0, 22.0, "left")]
    else:
        result = cua_ops.handle_cua_op("cua_click", payload)
        assert result["error"] == "foreground_required"
        assert clicks == []


@pytest.mark.parametrize("bounds", [[0, 0, 0, 10], [0, 0, float("nan"), 10]])
def test_element_click_center_rejects_invalid_bounds(fake_backend, monkeypatch, bounds):
    monkeypatch.setattr(fake_backend, "row_of", lambda e: {"bounds": bounds})
    with pytest.raises(cua_ops.CuaOpError, match="element_unavailable"):
        cua_ops._element_center(fake_backend.window)


def test_element_coordinate_fallback_rejects_background_window_of_same_app(
    fake_backend, monkeypatch
):
    cua_ops.handle_cua_op("cua_state", {"pid": 4242, "window_id": 0})
    original = fake_backend.pick_window

    def background(pid, window_id):
        element, info = original(pid, window_id)
        return element, {**info, "focused": False}

    def unsupported(*args):
        raise KeyError("no actions")

    monkeypatch.setattr(fake_backend, "pick_window", background)
    monkeypatch.setattr(fake_backend, "perform", unsupported)
    fake_backend.click_point = lambda *args: pytest.fail("background coordinates must not click")
    result = cua_ops.handle_cua_op(
        "cua_click", {"pid": 4242, "window_id": 0, "target": {"type": "element", "index": 1}}
    )
    assert result["error"] == "foreground_required"


def test_state_omits_unnamed_uia_invoke_groups_but_keeps_controls():
    rows = [
        {"depth": 0, "kind": "Group", "actions": ["Invoke"]},
        {"depth": 1, "kind": "Button", "actions": ["Invoke"]},
        {"depth": 1, "kind": "Group", "title": "Document", "actions": ["Invoke"]},
        {"depth": 1, "kind": "Group", "actions": ["Expand"]},
    ]
    state = cua_ops._render_tree(rows, {"title": "WPS", "window_id": 0}, False)
    assert "[0]" not in state
    assert "[1] Button" in state
    assert "[2] Group 'Document'" in state
    assert "[3] Group" in state


def test_event_scroll_rejects_background_window_of_same_app(fake_backend, monkeypatch):
    original = fake_backend.pick_window
    monkeypatch.setattr(
        fake_backend,
        "pick_window",
        lambda *args: (original(*args)[0], {**original(*args)[1], "focused": False}),
    )
    monkeypatch.setattr(fake_backend, "scroll_point", lambda *args: pytest.fail("background input"))
    result = cua_ops.handle_cua_op("cua_scroll", {"pid": 4242, "scroll_direction": "down"})
    assert result["error"] == "foreground_required"


def _two_windows(fake_backend, monkeypatch):
    a = fake_backend.window
    b = _FakeElement("AXWindow", "Other", [_FakeElement("AXButton", "B button")])

    def pick(pid, window_id):
        selected = 0 if window_id is None else window_id
        root = a if selected == 0 else b
        return root, {
            "window_id": selected,
            "title": root.title,
            "bounds": [0, 0, 800, 600],
            "focused": selected == 0,
        }

    monkeypatch.setattr(fake_backend, "pick_window", pick)
    cua_ops.handle_cua_op("cua_state", {"pid": 4242, "window_id": 0})
    cua_ops.handle_cua_op("cua_state", {"pid": 4242, "window_id": 1})
    return a, b


def test_subtree_without_window_id_uses_latest_window(fake_backend, monkeypatch):
    _two_windows(fake_backend, monkeypatch)
    result = cua_ops.handle_cua_op(
        "cua_state",
        {"pid": 4242, "target": {"type": "element", "index": 1}, "include_screenshot": True},
    )
    assert result["window"]["window_id"] == 1
    assert "[0] AXButton 'B button'" in result["state"]
    assert result["screenshot"]["error"] == "foreground_required"


@pytest.mark.parametrize("op", ["cua_click", "cua_scroll", "cua_type"])
def test_element_event_fallback_checks_its_observed_window(fake_backend, monkeypatch, op):
    _two_windows(fake_backend, monkeypatch)

    def unsupported(*args):
        raise KeyError("unsupported")

    monkeypatch.setattr(fake_backend, "perform", unsupported)
    monkeypatch.setattr(fake_backend, "set_value", unsupported)

    def unexpected(*args):
        pytest.fail("must reject event input on a background observation")

    monkeypatch.setattr(fake_backend, "scroll_point", unexpected)
    monkeypatch.setattr(cua_ops, "_type_text", unexpected)
    result = cua_ops.handle_cua_op(
        op,
        {
            "pid": 4242,
            "target": {"type": "element", "index": 1},
            "scroll_direction": "down",
            "text": "X",
        },
    )
    assert result["error"] == "foreground_required"


@pytest.mark.parametrize("complete", [True, False])
def test_subtree_observation_refreshes_snapshot_backend(fake_backend, monkeypatch, complete):
    cua_ops.handle_cua_op("cua_state", {"pid": 4242})
    refreshed = _FakeElement("AXTextField", "Updated text")

    def refresh(element, window):
        window["driver_complete"] = complete
        return refreshed

    monkeypatch.setattr(fake_backend, "refresh_element", refresh, raising=False)
    result = cua_ops.handle_cua_op(
        "cua_state", {"pid": 4242, "target": {"type": "element", "index": 2}}
    )
    assert "Updated text" in result["state"]
    assert result["truncated"] is not complete
    cua_ops.handle_cua_op("cua_click", {"pid": 4242, "target": {"type": "element", "index": 0}})
    assert fake_backend.performed[-1][0] is refreshed


def test_subtree_screenshot_crops_to_element_and_maps_pixels(fake_backend, monkeypatch):
    captures = []
    monkeypatch.setattr(
        fake_backend,
        "row_of",
        lambda e: {"kind": e.kind, "title": e.title, "bounds": [100, 100, 200, 100]},
    )
    monkeypatch.setattr(
        cua_ops,
        "_capture",
        lambda bounds, window=None: captures.append(bounds) or {"width": 100, "height": 50},
    )
    cua_ops.handle_cua_op("cua_state", {"pid": 4242})
    result = cua_ops.handle_cua_op(
        "cua_state",
        {"pid": 4242, "target": {"type": "element", "index": 1}, "include_screenshot": True},
    )
    assert captures == [[100, 100, 200, 100]]
    assert result["screenshot"]["bounds"] == [100, 100, 200, 100]
    points = []
    monkeypatch.setattr(
        fake_backend,
        "click_point",
        lambda x, y, *a, **k: points.append((x, y)) or {},
        raising=False,
    )
    cua_ops.handle_cua_op(
        "cua_snapshot_action",
        {
            "operation": "click",
            "pid": 4242,
            "snapshot_id": result["snapshot_id"],
            "coordinate_space": "screenshot",
            "target": {"x": 50, "y": 25},
        },
    )
    assert points == [(200, 150)]


def test_capture_reports_size_and_keeps_text_lossless_when_within_budget(fake_backend, monkeypatch):
    import base64

    from PIL import Image

    image = Image.new("RGB", (1800, 1000), "white")
    monkeypatch.setattr(
        fake_backend, "screenshot", lambda bounds, window=None: image, raising=False
    )
    result = cua_ops._capture([0, 0, 1800, 1000])
    assert result["width"] == 1800
    assert result["mime"] == "image/png"
    assert result["size"] == len(base64.b64decode(result["data_b64"]))


@pytest.mark.parametrize("element", [[900, 20, 20, 20], None, [0, 0, float("nan"), 20]])
def test_invalid_crop_never_captures_other_desktop_regions(element):
    with pytest.raises(cua_ops.CuaOpError, match="screenshot_failed"):
        cua_ops._intersect_bounds([10, 20, 800, 600], element)


def test_crop_clips_element_to_window():
    assert cua_ops._intersect_bounds([10, 20, 800, 600], [0, 0, 100, 100]) == [10, 20, 90, 80]


def test_focus_lost_during_capture_discards_pixels(fake_backend, monkeypatch):
    focus = [4242]
    monkeypatch.setattr(fake_backend, "frontmost_pid", lambda: focus[0])

    def capture(bounds, window=None):
        focus[0] = 100
        return {"data_b64": "private pixels", "width": 100, "height": 100}

    monkeypatch.setattr(cua_ops, "_capture", capture)
    result = cua_ops.handle_cua_op("cua_state", {"pid": 4242, "include_screenshot": True})
    assert result["screenshot"]["error"] == "foreground_required"
    assert "data_b64" not in result["screenshot"]
    assert cua_ops._get_observation(4242, None).screenshot is None


def test_hidden_rows_do_not_exhaust_visible_budget_or_hide_visible_descendants(
    fake_backend, monkeypatch
):
    target = _FakeElement("button", "Answer")
    hidden_parent = _FakeElement("group", "hidden layout", [target])
    offscreen = _FakeElement("button", "Below fold")
    hidden = [hidden_parent, *[_FakeElement("button", "hidden template") for _ in range(10)]]
    fake_backend.window.children = [*hidden, offscreen]
    original = fake_backend.row_of

    def row_of(element):
        row = original(element)
        if element in hidden or element is fake_backend.window:
            row["states"] = ["hidden"]
        elif element is offscreen:
            row["states"] = ["offscreen"]
        return row

    monkeypatch.setattr(fake_backend, "row_of", row_of)
    monkeypatch.setattr(cua_ops, "STATE_MAX_ELEMENTS", 3)
    state = cua_ops.handle_cua_op("cua_state", {"pid": 4242})
    assert not state["truncated"]
    assert "hidden template" not in state["state"]
    assert "[0] AXWindow" in state["state"]
    assert "[2] button 'Below fold'" in state["state"]
    assert "[1] button 'Answer'" in state["state"]
    clicked = cua_ops.handle_cua_op(
        "cua_click",
        {
            "pid": 4242,
            "snapshot_id": state["snapshot_id"],
            "target": {"type": "element", "index": 1},
        },
    )
    assert "error" not in clicked
    assert fake_backend.performed[-1][0] is target


def test_on_screen_controls_take_budget_before_offscreen_content(fake_backend, monkeypatch):
    target = _FakeElement("button", "Visible answer")
    offscreen = [_FakeElement("text", f"Footer {index}") for index in range(10)]
    parent = _FakeElement("group", "Question", [target])
    fake_backend.window.children = [*offscreen, parent]
    original = fake_backend.row_of

    def row_of(element):
        row = original(element)
        if element in offscreen:
            row["states"] = ["offscreen"]
        return row

    monkeypatch.setattr(fake_backend, "row_of", row_of)
    monkeypatch.setattr(cua_ops, "STATE_MAX_ELEMENTS", 4)
    state = cua_ops.handle_cua_op("cua_state", {"pid": 4242})
    assert state["truncated"]
    assert "Visible answer" in state["state"]
    assert "Footer 0" in state["state"]
    observation = cua_ops._get_observation(4242, None)
    index = observation.elements.index(target)
    result = cua_ops.handle_cua_op(
        "cua_click",
        {
            "pid": 4242,
            "snapshot_id": state["snapshot_id"],
            "target": {"type": "element", "index": index},
        },
    )
    assert "error" not in result
    assert fake_backend.performed[-1][0] is target


@pytest.mark.parametrize(
    "text,modifiers,keys,mods",
    [
        ("return", None, ["enter"], []),
        ("ctrl+shift+a", None, ["a"], ["ctrl", "shift"]),
        ("l", "ctrl", ["l"], ["ctrl"]),
    ],
)
def test_key_routes_to_one_window_bound_driver(
    fake_backend, monkeypatch, text, modifiers, keys, mods
):
    cua_ops.handle_cua_op("cua_state", {"pid": 4242})
    calls = []
    monkeypatch.setattr(
        fake_backend, "press_chord", lambda k, m, w: calls.append((k, m, w["window_id"])) or {}
    )
    result = cua_ops.handle_cua_op("cua_key", {"pid": 4242, "text": text, "modifiers": modifiers})
    assert result["ok"] and result["strategy"] == "agent-desktop"
    assert calls == [(keys, mods, 0)]


def test_raw_text_routes_unicode_literally_to_driver(fake_backend, monkeypatch):
    calls = []
    monkeypatch.setattr(
        fake_backend,
        "type_text",
        lambda text, window: calls.append((text, window["window_id"])) or {},
    )
    result = cua_ops.handle_cua_op("cua_type", {"pid": 4242, "text": "中文 {ENTER}+^%~()\n😀"})
    assert result["ok"]
    assert calls == [("中文 {ENTER}+^%~()\n😀", 0)]


@pytest.mark.parametrize(
    "target,point",
    [
        ({"type": "element", "index": 1}, (51.0, 22.0)),
        ({"type": "coordinate", "x": 100, "y": 200}, (100.0, 200.0)),
        ({}, (410.0, 320.0)),
    ],
)
def test_scroll_routes_position_and_wheel_in_one_driver_call(
    fake_backend, monkeypatch, target, point
):
    calls = []
    cua_ops.handle_cua_op("cua_state", {"pid": 4242})
    monkeypatch.setattr(fake_backend, "scroll_point", lambda *args: calls.append(args) or {})
    result = cua_ops.handle_cua_op(
        "cua_scroll", {"pid": 4242, "target": target, "scroll_direction": "down"}
    )
    assert result["ok"]
    assert calls == [(*point, "down", 10)]


@pytest.mark.parametrize(
    "app,args",
    [("firefox", ["https://example.com"]), ("/Applications/Office.app", ["--safe", "a b"])],
)
def test_app_launch_routes_arguments_without_shell(fake_backend, monkeypatch, app, args):
    calls = []
    monkeypatch.setattr(fake_backend, "launch", lambda a, b: calls.append((a, b)) or {"pid": 7})
    result = cua_ops.handle_cua_op("cua_launch", {"app": app, "args": args})
    assert result["ok"]
    assert calls == [(app, args)]


def test_status_cannot_claim_ready_when_lock_check_is_unavailable(fake_backend, monkeypatch):
    def unavailable():
        raise ImportError("missing session guard")

    monkeypatch.setattr(fake_backend, "desktop_locked", unavailable, raising=False)
    result = cua_ops.handle_cua_op("cua_status", {})
    assert result["ready"] is False and result["platform"] == "fake"
