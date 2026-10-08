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


class _FakeBackend:
    platform_name = "fake"

    def __init__(self):
        self.performed: list[tuple[Any, str]] = []
        self.set_values: list[tuple[Any, str]] = []
        self.window = _FakeElement(
            "AXWindow",
            "Main",
            [_FakeElement("AXButton", "确定"), _FakeElement("AXTextField", "搜索")],
        )

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
        return self.window, {"window_id": 0, "title": "Main", "bounds": [10.0, 20.0, 800.0, 600.0]}

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
        self.set_values.append((element, text))


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


def test_state_walks_tree_and_stores_indices(fake_backend: _FakeBackend) -> None:
    result = cua_ops.handle_cua_op("cua_state", {"pid": 4242})
    assert result["element_count"] == 3  # 窗口 + 按钮 + 输入框
    assert "[0] AXWindow 'Main'" in result["state"]
    assert "[1] AXButton '确定'" in result["state"]
    observed = cua_ops._OBSERVATIONS["4242:0"]
    assert len(observed.elements) == 3


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
