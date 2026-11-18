"""Pinned driver integration preserves machine/window identity and failure semantics."""

from types import SimpleNamespace

import pytest


@pytest.fixture
def backend(monkeypatch, tmp_path):
    from lambchat_sandbox import cua_backend
    from lambchat_sandbox.agent_desktop import AgentDesktopBackend

    monkeypatch.setattr(cua_backend, "backend_platform", lambda: "darwin")
    instance = AgentDesktopBackend(tmp_path / "agent-desktop")
    return instance


def test_windows_filter_same_named_processes(backend, monkeypatch):
    windows = [
        {
            "id": "w-42",
            "pid": 7,
            "title": "Target",
            "is_focused": True,
            "bounds": {"x": 10, "y": 20, "width": 800, "height": 600},
        },
        {"id": "w-43", "pid": 8, "title": "Other instance"},
    ]
    calls = []
    monkeypatch.setattr(
        backend,
        "_call",
        lambda *a, **k: (
            calls.append(a)
            or ({"apps": [{"pid": 7, "name": "Editor"}]} if a[0] == "list-apps" else windows)
        ),
    )
    rows = backend.windows(7)
    assert len(rows) == 1
    assert rows[0]["window_id"] == 42
    assert rows[0]["bounds"] == [10, 20, 800, 600]
    assert calls == [("list-apps",), ("list-windows", "--app", "Editor", "--timeout-ms", "5000")]


@pytest.mark.parametrize("owner,enabled", [(None, True), ("7", True), ("8", True), ("7", False)])
def test_control_surfaces_are_not_agent_targets(backend, monkeypatch, owner, enabled):
    monkeypatch.setenv("LAMBCHAT_DESKTOP_CONTROL", "fixture" if enabled else "")
    if owner is None:
        monkeypatch.delenv("LAMBCHAT_DESKTOP_CONTROL_OWNER_PID", raising=False)
    else:
        monkeypatch.setenv("LAMBCHAT_DESKTOP_CONTROL_OWNER_PID", owner)
    rows = [
        {"id": f"w-{index}", "pid": 7, "title": title, "is_focused": index == 42}
        for index, title in enumerate(
            ["LambChat Control", "LambChat Control Overlay", "LambChat"], 41
        )
    ]
    monkeypatch.setattr(
        backend,
        "_call",
        lambda *args, **kwargs: (
            {"apps": [{"pid": 7, "name": "Editor"}]} if args[0] == "list-apps" else rows
        ),
    )
    if owner == "7" and enabled:
        assert [w["title"] for w in backend.windows(7)] == ["LambChat"]
        assert backend.pick_window(7, None)[1]["window_id"] == 43
        with pytest.raises(KeyError):
            backend.pick_window(7, 42)
    else:
        assert len(backend.windows(7)) == 3
        assert backend.pick_window(7, 42)[1]["title"] == "LambChat Control Overlay"


def test_set_value_uses_qualified_ref_and_stdin(backend, monkeypatch):
    calls = []
    monkeypatch.setattr(
        backend,
        "_call",
        lambda *a, **k: calls.append((a, k)) or {"disposition": {"delivery": "delivered_verified"}},
    )
    monkeypatch.setattr(backend, "_enable_cursor", lambda: None)
    result = backend.set_value({"ref_id": "@snapshot:e2"}, "中文\nsecret")
    assert calls == [(("set-value", "@snapshot:e2", "--stdin"), {"text": "中文\nsecret"})]
    assert result["disposition"]["delivery"] == "delivered_verified"


def test_refused_action_does_not_fallback_to_physical_input(backend, monkeypatch):
    from lambchat_sandbox.cua_ops import CuaOpError

    def reject(*args, **kwargs):
        raise CuaOpError("stale_state", "ambiguous target")

    monkeypatch.setattr(backend, "_call", reject)
    monkeypatch.setattr(backend, "_enable_cursor", lambda: None)
    with pytest.raises(CuaOpError, match="stale_state"):
        backend.perform({"ref_id": "@snapshot:e2"}, "click")


def test_native_double_click_is_one_command_with_count(backend, monkeypatch):
    calls = []
    monkeypatch.setattr(backend, "_call", lambda *a, **k: calls.append(a) or {})
    monkeypatch.setattr(backend, "_enable_cursor", lambda: None)
    backend.click_point(10, 20, "left", count=2)
    assert calls == [("--headed", "mouse-click", "--xy=10,20", "--button", "left", "--count", "2")]


def test_linux_opaque_window_identity_is_preserved(backend, monkeypatch):
    native_id = "w-atspi-opaque-bus-and-path"
    monkeypatch.setattr(
        backend,
        "_call",
        lambda *a, **k: (
            {"apps": [{"pid": 7, "name": "Editor"}]}
            if a[0] == "list-apps"
            else [{"id": native_id, "pid": 7, "title": "Target", "is_focused": True}]
        ),
    )
    first = backend.windows(7)[0]
    assert first["driver_window_id"] == native_id
    assert 0 <= first["window_id"] < 2**53
    assert backend.windows(7)[0]["window_id"] == first["window_id"]


def test_overlay_unavailable_does_not_replay_or_prevent_semantic_action(backend, monkeypatch):
    from lambchat_sandbox.cua_ops import CuaOpError

    calls = []
    monkeypatch.setattr(backend, "_session", lambda: "session-1")

    def call(*args, **kwargs):
        calls.append(args)
        if args[0] == "cursor-overlay":
            raise CuaOpError("platform_not_supported")
        return {"disposition": {"delivery": "delivered_verified"}}

    monkeypatch.setattr(backend, "_call", call)
    result = backend.perform({"ref_id": "@snapshot:e1"}, "click")
    assert result["disposition"]["delivery"] == "delivered_verified"
    assert len(calls) == 2
    assert calls[0][:2] == ("cursor-overlay", "enable")
    assert calls[0][calls[0].index("--rim") + 1] == "#FFFFFF"
    assert calls[0][calls[0].index("--accent") + 1] == "#1F8CFF"
    assert calls[1] == ("click", "@snapshot:e1")


def test_linux_scroll_explicitly_uses_headed_mode(backend, monkeypatch):
    from lambchat_sandbox import cua_backend

    calls = []
    monkeypatch.setattr(cua_backend, "backend_platform", lambda: "linux")
    monkeypatch.setattr(backend, "_enable_cursor", lambda: None)
    monkeypatch.setattr(backend, "_call", lambda *a, **k: calls.append(a) or {})
    backend.scroll_element({"ref_id": "@snapshot:e1"}, "down", 1)
    assert calls == [
        ("--headed", "scroll", "@snapshot:e1", "--direction", "down", "--amount", "10")
    ]


@pytest.mark.parametrize("platform", ["linux", "win32"])
def test_resolves_driver_app_name_without_global_accessibility_scan(backend, monkeypatch, platform):
    from lambchat_sandbox import cua_backend

    calls = []
    monkeypatch.setattr(cua_backend, "backend_platform", lambda: platform)

    def call(*args, **kwargs):
        calls.append(args)
        if args[0] == "list-apps":
            return {"apps": [{"pid": 7, "name": "python3.14"}]}
        return [{"id": "w-42", "pid": 7, "title": "Target"}]

    monkeypatch.setattr(backend, "_call", call)
    assert backend.windows(7)[0]["window_id"] == 42
    assert calls[1] == ("list-windows", "--app", "python3.14", "--timeout-ms", "5000")


@pytest.mark.parametrize(
    ("action", "command"),
    [
        ("SetFocus", "focus"),
        ("RightClick", "right-click"),
        ("ScrollTo", "scroll-to"),
        ("Check", "check"),
        ("Uncheck", "uncheck"),
        ("Hover", "hover"),
    ],
)
def test_reported_parameterless_action_is_supported(backend, monkeypatch, action, command):
    calls = []
    monkeypatch.setattr(backend, "_enable_cursor", lambda: None)
    monkeypatch.setattr(backend, "_call", lambda *a, **k: calls.append(a) or {})
    backend.perform({"ref_id": "@snapshot:e1"}, action)
    prefix = ("--headed",) if command in {"focus", "hover"} else ()
    assert calls == [(*prefix, command, "@snapshot:e1")]


def test_cursor_reports_unrendered_without_claiming_visibility(backend, monkeypatch):
    monkeypatch.setattr(backend, "_session", lambda: "session-1")
    monkeypatch.setattr(backend, "_call", lambda *a, **k: {"rendered": False})
    assert backend._enable_cursor() == {"rendered": False}


def test_subtree_refresh_reads_live_value_instead_of_cached_snapshot(backend, monkeypatch):
    calls = []
    monkeypatch.setattr(
        backend,
        "_call",
        lambda *a, **k: (
            calls.append(a)
            or {"tree": {"ref_id": "@s:e2", "role": "textfield", "value": "new"}, "complete": True}
        ),
    )
    window = {}
    refreshed = backend.refresh_element(
        {"ref_id": "@s:e2", "role": "textfield", "value": "old"}, window
    )
    assert refreshed["value"] == "new"
    assert window["driver_complete"] is True
    assert calls == [
        ("snapshot", "--root", "@s:e2", "--compact", "--include-bounds", "--timeout-ms", "5000")
    ]


@pytest.mark.parametrize("complete", [False, None])
def test_incomplete_subtree_is_not_reported_as_complete(backend, monkeypatch, complete):
    result = {"tree": {"ref_id": "@s:e2", "role": "group"}}
    if complete is not None:
        result["complete"] = complete
    monkeypatch.setattr(backend, "_call", lambda *a, **k: result)
    window = {"driver_complete": True}
    backend.refresh_element({"ref_id": "@s:e2"}, window)
    assert window["driver_complete"] is False


def test_snapshot_owner_check_uses_resolved_driver_app_without_rediscovery(backend, monkeypatch):
    calls = []

    def call(*args, **kwargs):
        calls.append(args)
        if args[0] == "snapshot":
            return {
                "app": "Driver Editor",
                "window": {"id": "w-42"},
                "tree": {"role": "window"},
                "complete": True,
            }
        return [{"id": "w-42", "pid": 7, "title": "Target"}]

    monkeypatch.setattr(backend, "_call", call)
    assert (
        backend._node({"_window": {"driver_window_id": "w-42", "window_id": 42}, "_pid": 7})["role"]
        == "window"
    )
    assert calls[-1] == ("list-windows", "--app", "Driver Editor", "--timeout-ms", "5000")


def test_action_result_omits_transport_diagnostics_but_preserves_delivery_evidence(
    backend, monkeypatch
):
    import json
    import subprocess

    data = {
        "action": "set-value",
        "disposition": {"delivery": "delivered_verified", "retry": "unsafe"},
        "post_state": {"value": "new"},
        "details": {"auto_wait": {"lease_hold_ms": 42}, "application_commit": "not_verified"},
        "steps": [{"mechanism": "semantic_api"}],
    }
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *a, **k: SimpleNamespace(stdout=json.dumps({"ok": True, "data": data})),
    )
    result = backend._run(["set-value", "@s:e1"])
    assert result == {
        "action": "set-value",
        "disposition": data["disposition"],
        "post_state": data["post_state"],
        "details": {"application_commit": "not_verified"},
    }


def test_driver_error_keeps_delivery_and_recovery_as_structured_evidence(backend, monkeypatch):
    import json
    import subprocess

    from lambchat_sandbox.cua_ops import CuaOpError

    error = {
        "code": "ACTION_FAILED",
        "message": "Readback failed after input",
        "disposition": {"delivery": "delivery_uncertain", "retry": "unsafe"},
        "post_state": {"value": "partially written"},
    }
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *a, **k: SimpleNamespace(stdout=json.dumps({"ok": False, "error": error})),
    )
    with pytest.raises(CuaOpError) as caught:
        backend._run(["set-value", "@s:e1"])
    assert caught.value.context["disposition"] == error["disposition"]
    assert caught.value.context["post_state"] == error["post_state"]


def test_scroll_preserves_native_delivery_report(backend, monkeypatch):
    report = {"disposition": {"delivery": "delivered_unverified", "retry": "unsafe"}}
    monkeypatch.setattr(backend, "_enable_cursor", lambda: None)
    monkeypatch.setattr(backend, "_call", lambda *a, **k: report)
    assert backend.scroll_element({"ref_id": "@s:e1"}, "down", 1) == report


@pytest.mark.parametrize("owner_pid", [8, None])
def test_snapshot_owner_recheck_rejects_changed_process(backend, monkeypatch, owner_pid):
    from lambchat_sandbox.cua_ops import CuaOpError

    def call(*args, **kwargs):
        if args[0] == "snapshot":
            return {"app": "Editor", "window": {"id": "w-42"}, "tree": {"role": "window"}}
        return [{"id": "w-42", "pid": owner_pid, "title": "Target"}]

    monkeypatch.setattr(backend, "_call", call)
    with pytest.raises(CuaOpError, match="stale_state"):
        backend._node({"_window": {"driver_window_id": "w-42", "window_id": 42}, "_pid": 7})


def test_non_actionable_subtree_without_reference_has_structured_error(backend):
    from lambchat_sandbox.cua_ops import CuaOpError

    with pytest.raises(CuaOpError, match="element_unavailable"):
        backend.refresh_element({"role": "text", "name": "27/30"}, {})


def test_non_actionable_subtree_refreshes_by_verified_window_path(backend, monkeypatch):
    old = {
        "role": "text",
        "name": "score",
        "value": "old",
        "_driver_path": [0],
        "_driver_owner": {"_window": {"driver_window_id": "w-42"}, "_pid": 7},
    }
    fresh = {"role": "text", "name": "score", "value": "new"}
    monkeypatch.setattr(
        backend, "_node", lambda element: {"children": [fresh]} if "_window" in element else element
    )
    assert backend.refresh_element(old, {})["value"] == "new"
    fresh["name"] = "other"
    from lambchat_sandbox.cua_ops import CuaOpError

    with pytest.raises(CuaOpError, match="stale_state"):
        backend.refresh_element(old, {})


def test_wayland_keeps_driver_focus_for_accessibility_actions(backend, monkeypatch):
    from lambchat_sandbox import cua_backend

    monkeypatch.setenv("WAYLAND_DISPLAY", "wayland-0")
    monkeypatch.setattr(cua_backend, "backend_platform", lambda: "linux")
    monkeypatch.setattr(
        backend,
        "_call",
        lambda *args: (
            {"apps": [{"pid": 7, "name": "Editor"}]}
            if args[0] == "list-apps"
            else [{"id": "w-42", "pid": 7, "title": "Target", "is_focused": True}]
        ),
    )
    assert backend.windows(7)[0]["focused"] is True


def test_read_only_subtree_refresh_uses_verified_path_when_driver_ref_is_ambiguous(
    backend, monkeypatch
):
    from lambchat_sandbox.cua_ops import CuaOpError

    old = {
        "role": "group",
        "name": "main",
        "bounds": {"x": 0, "y": 0, "width": 800, "height": 600},
        "ref_id": "@s:e1",
        "_driver_path": [0],
        "_driver_owner": {"_window": {"driver_window_id": "w-42"}, "_pid": 7},
    }
    fresh = {**old, "children": [{"role": "button", "name": "Current answer"}]}
    monkeypatch.setattr(
        backend, "_node", lambda element: {"children": [fresh]} if "_window" in element else element
    )

    def reject_reference(*args):
        raise CuaOpError(
            "stale_state", "not unique", context={"details": {"kind": "identity_not_unique"}}
        )

    monkeypatch.setattr(backend, "_call", reject_reference)
    assert backend.refresh_element(old, {})["children"][0]["name"] == "Current answer"
    fresh["name"] = "Other panel"
    with pytest.raises(CuaOpError, match="stale_state"):
        backend.refresh_element(old, {})


@pytest.mark.parametrize("platform", ["win32", "darwin", "linux"])
def test_apps_and_windows_share_driver_identity(backend, monkeypatch, platform):
    from lambchat_sandbox import cua_backend

    monkeypatch.setattr(cua_backend, "backend_platform", lambda: platform)
    calls = []

    def call(*args):
        calls.append(args)
        if args[0] == "list-apps":
            return {"apps": [{"pid": 42, "name": "Browser"}]}
        return [{"id": "w-8", "pid": 42, "title": "Browser"}]

    monkeypatch.setattr(backend, "_call", call)
    assert backend.list_apps() == [{"pid": 42, "name": "Browser"}]
    assert backend.windows(42)[0]["window_id"] == 8
    assert calls == [
        ("list-apps",),
        ("list-apps",),
        ("list-windows", "--app", "Browser", "--timeout-ms", "5000"),
    ]


def test_missing_driver_never_silently_switches_discovery_backend(monkeypatch):
    from lambchat_sandbox import agent_desktop, cua_backend

    monkeypatch.setattr(cua_backend, "_BACKEND", None)
    monkeypatch.setattr(cua_backend, "_BACKEND_ERROR", None)
    monkeypatch.setattr(cua_backend, "sys", SimpleNamespace(platform="win32"))
    monkeypatch.setattr(agent_desktop, "binary_path", lambda: None)
    for _ in range(2):
        with pytest.raises(cua_backend.UnsupportedBackendError, match="agent_desktop_missing"):
            cua_backend.backend()
        assert cua_backend._BACKEND is None


def test_driver_discovery_failure_does_not_mix_native_results(backend, monkeypatch):
    from lambchat_sandbox.cua_ops import CuaOpError

    def fail(*args):
        raise CuaOpError("access_denied", "interactive desktop unavailable")

    monkeypatch.setattr(backend, "_call", fail)
    for observe in (backend.list_apps, lambda: backend.windows(7)):
        with pytest.raises(CuaOpError, match="access_denied"):
            observe()


def test_disappeared_app_requires_rediscovery_without_guessing_native_pid(backend, monkeypatch):
    responses = iter([{"apps": [{"pid": 7, "name": "Editor"}]}, {"apps": []}])
    monkeypatch.setattr(backend, "_call", lambda *args: next(responses))
    assert backend.list_apps()[0]["pid"] == 7
    with pytest.raises(KeyError, match="app_not_found"):
        backend.windows(7)


@pytest.mark.parametrize(
    "key,color", [("agent-1", "#FFE485"), ("agent-11", "#BCACDD"), ("B", "#F698DB")]
)
def test_cursor_color_uses_the_observing_chat_not_the_temporary_driver_session(
    backend, monkeypatch, key, color
):
    from lambchat_sandbox.cua_ops import _OBSERVATION_SESSION

    monkeypatch.setattr(backend, "_session", lambda: "temporary-session")
    calls = []
    monkeypatch.setattr(backend, "_call", lambda *args: calls.append(args) or {"rendered": True})
    token = _OBSERVATION_SESSION.set(key)
    try:
        backend._enable_cursor()
        backend._enable_cursor()
    finally:
        _OBSERVATION_SESSION.reset(token)
    assert len(calls) == 1
    assert calls[0][calls[0].index("--accent") + 1] == color
