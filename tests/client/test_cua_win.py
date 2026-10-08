"""cua_win 跨平台单元测试:pywinauto 懒加载后本模块在任意平台可导入,
用假元素/假窗口驱动纯逻辑(语义映射/聚焦/激活/apps 过滤)。

真机行为(UIA 真实枚举、set_focus 真激活)仍靠发版前的 Windows 抽检。
"""

from __future__ import annotations

from typing import Any

import pytest

from lambchat_sandbox import cua_win


class _FakeWinElement:
    def __init__(self, methods: list[str] | None = None, legacy: Any = None, pid: int = 1):
        self.calls: list[str] = []
        self._methods = methods or []
        self.iface_legacy = legacy
        self._pid = pid

    def __getattr__(self, name: str) -> Any:
        # hasattr 探测的方法只有列在 _methods 里的才算存在
        if name.startswith("__"):
            raise AttributeError(name)

        def _call(*args: Any, **kwargs: Any) -> Any:
            self.calls.append(name)
            return True

        if name in self._methods or name in ("set_focus", "process_id"):
            return _call
        raise AttributeError(name)

    def process_id(self) -> int:
        self.calls.append("process_id")
        return self._pid


class _Legacy:
    def __init__(self) -> None:
        self.default_action_called = False

    def DoDefaultAction(self) -> None:  # noqa: N802 - COM 命名
        self.default_action_called = True


def test_perform_maps_semantic_click_to_invoke() -> None:
    """生产事故回归(2026-10-08):click 语义没映射,Windows 元素点击整体
    KeyError「action click not available on element」。"""
    element = _FakeWinElement(methods=["invoke"])
    cua_win.perform(element, "click")
    assert "invoke" in element.calls


def test_perform_maps_press_and_axpress() -> None:
    element = _FakeWinElement(methods=["invoke"])
    cua_win.perform(element, "press")
    cua_win.perform(element, "AXPress")
    assert element.calls.count("invoke") == 2


def test_perform_falls_back_to_legacy_default_action() -> None:
    legacy = _Legacy()
    element = _FakeWinElement(methods=["select"], legacy=legacy)
    cua_win.perform(element, "click")
    assert legacy.default_action_called


def test_perform_unavailable_raises_key_error() -> None:
    element = _FakeWinElement(methods=["select"])
    with pytest.raises(KeyError):
        cua_win.perform(element, "click")


def test_set_focus_delegates_to_wrapper() -> None:
    element = _FakeWinElement()
    cua_win.set_focus(element)
    assert "set_focus" in element.calls


def test_activate_window_focuses_pinned_window(monkeypatch: pytest.MonkeyPatch) -> None:
    handles = [_FakeWinElement(pid=7), _FakeWinElement(pid=7)]

    def _fake_windows(pid: int) -> list[dict[str, Any]]:
        assert pid == 7
        return [
            {"window_id": 0, "title": "A", "handle": handles[0]},
            {"window_id": 1, "title": "B", "handle": handles[1]},
        ]

    monkeypatch.setattr(cua_win, "windows", _fake_windows)
    cua_win.activate_window(7, 1)
    assert "set_focus" in handles[1].calls
    assert "set_focus" not in handles[0].calls


def test_activate_window_without_id_picks_main(monkeypatch: pytest.MonkeyPatch) -> None:
    handle = _FakeWinElement(pid=7)
    monkeypatch.setattr(
        cua_win, "windows", lambda pid: [{"window_id": 0, "title": "A", "handle": handle}]
    )
    cua_win.activate_window(7, None)
    assert "set_focus" in handle.calls


def test_activate_window_no_windows_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cua_win, "windows", lambda pid: [])
    with pytest.raises(KeyError):
        cua_win.activate_window(7, None)


def test_list_apps_keeps_only_window_owning_processes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """生产事故回归(2026-10-08):全量 tasklist 数百行系统进程,模型只能
    盲探 pid(连续 6 次 no_windows)。只回持有窗口的 GUI 进程。"""
    monkeypatch.setattr(
        cua_win, "_desktop_windows", lambda: [_FakeWinElement(pid=100), _FakeWinElement(pid=300)]
    )

    class _Tasklist:
        stdout = (
            '"System","4","N/A"\n'
            '"svchost.exe","200","N/A"\n'
            '"msedge.exe","100","N/A"\n'
            '"chrome.exe","300","N/A"\n'
        )

    monkeypatch.setattr("subprocess.run", lambda *a, **k: _Tasklist())
    monkeypatch.setattr(cua_win, "frontmost_pid", lambda: 300)
    rows = cua_win.list_apps()
    assert [r["pid"] for r in rows] == [300, 100]  # 前台优先
    assert all(r["name"] in ("msedge", "chrome") for r in rows)


def test_list_apps_without_gui_windows_returns_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cua_win, "_desktop_windows", lambda: [])
    assert cua_win.list_apps() == []
