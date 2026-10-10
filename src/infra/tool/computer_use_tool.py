"""computer_use 工具：经本地沙箱 daemon 驱动用户 Mac 的图形界面。

复刻 ZCode computer-use 的语义契约：Accessibility 树优先的观察与操作、
元素索引寻址最近一次观察、事件兜底要求前台。**禁止 osascript / System
Events / AppleScript**——无人值守场景下 TCC 弹窗无人可点会永久卡死。

链路：agent 工具 → 本地 relay(dispatch_local_call)→ daemon cua_ops。
云端沙箱（e2b/daytona/cubesandbox）无此能力，daemon 不在线时报
offline 错误（模型可引导用户启动桌面端）。
"""

from __future__ import annotations

import asyncio
import hashlib
import json
from typing import Annotated, Any, Optional
from weakref import WeakValueDictionary

from langchain.tools import ToolRuntime, tool
from pydantic import BaseModel, Field

from src.infra.agent.events.binary_uploads import upload_binary_blocks
from src.infra.agent.middleware.sandbox_confirm import _lookup_confirm_policy
from src.infra.async_utils import run_long_blocking_io
from src.infra.logging import get_logger
from src.infra.sandbox.confirm import confirm_local_op
from src.infra.sandbox.relay.dispatch import dispatch_local_call
from src.infra.sandbox.relay.registry import SandboxClientRegistry
from src.infra.tool.backend_utils import (
    get_base_url_from_runtime,
    get_session_id_from_runtime,
    get_user_id_from_runtime,
)
from src.kernel.errors import AppError

logger = get_logger(__name__)
_CUA_LOCKS: WeakValueDictionary[tuple[asyncio.AbstractEventLoop, str, str], asyncio.Lock] = (
    WeakValueDictionary()
)


def _desktop_call_lock(user_id: str, machine_id: str) -> asyncio.Lock:
    # Preserve model call order before asynchronous policy/relay work can reorder input.
    key = (asyncio.get_running_loop(), user_id, machine_id)
    return _CUA_LOCKS.setdefault(key, asyncio.Lock())


async def resolve_computer_use_context(
    user_id: str, options: dict[str, Any], hitl_resume: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Pin the trusted session selection once per run, before any model tool call.

    自动档（会话未显式选机）按注册表缺省解析钉住目标机（默认机 → 唯一在线
    → legacy；默认机缺配时由注册表首台自动领养）——钉住的机器与显式选机走
    完全相同的确认门/目标校验/HITL 续作匹配，模型仍无法改指目标。无任何
    在线机时 machine_id 保持 None（工具按 machine_selection_required 收敛）。
    """
    choice = options.get("sandbox")
    platform = choice if choice in ("local", "cloud") else None
    selected = options.get("sandbox_machine_id")
    machine = selected.strip() if isinstance(selected, str) else None
    if not machine:
        # 自动档：注册表缺省解析钉默认机。尽力而为（照 _lookup_daemon_identity
        # 的容错语义）——redis 故障回落 None，工具层按 machine_selection_required
        # 收敛，不阻断会话启动。
        try:
            machine = await SandboxClientRegistry().resolve_target(user_id)
        except Exception:  # noqa: BLE001 - 选机解析尽力而为，失败不注入
            logger.warning("computer_use default machine resolution failed for user %s", user_id)
            machine = None
    selection: dict[str, Any] = {"platform": platform, "machine_id": machine}
    if hitl_resume and isinstance(hitl_resume.get("confirmation_context"), dict):
        approval = hitl_resume.get("approval_resolved") or {}
        selection["resume"] = {
            "tool_call_id": approval.get("tool_call_id"),
            "approved": approval.get("success") is True,
            "confirmation_context": hitl_resume["confirmation_context"],
        }
    return selection


_ACTIONS = (
    "status",
    "apps",
    "launch",
    "windows",
    "state",
    "activate",
    "click",
    "set_value",
    "type",
    "key",
    "scroll",
    "action",
)


class _ComputerUseInput(BaseModel):
    action: str = Field(
        ...,
        description=(
            "status|apps|launch|windows|state|activate|click|set_value|type|key|scroll|action"
        ),
    )
    url: Optional[str] = Field(None, description="launch: open this URL in the default browser")
    app: Optional[str] = Field(
        None, description="launch: executable path or macOS .app bundle (no shell)"
    )
    args: Optional[list[str]] = Field(None, description="launch: argv for app")
    machine_id: Optional[str] = Field(
        None,
        description="optional assertion of the session-selected machine; cannot change targets",
    )
    pid: Optional[int] = Field(
        None,
        description="Target app pid from apps. Required unless name is supplied for all actions except status/apps/launch, including coordinate clicks.",
    )
    name: Optional[str] = Field(None, description="target app name (exact, from apps)")
    window_id: Optional[int] = Field(None, description="pin one window (from windows)")
    index: Optional[int] = Field(
        None, description="element index from latest state; state: inspect only this subtree"
    )
    x: Optional[float] = Field(
        None,
        description="coordinate fallback: global screen x (add window origin; account for screenshot scaling)",
    )
    y: Optional[float] = Field(
        None,
        description="coordinate fallback: global screen y (add window origin; account for screenshot scaling)",
    )
    text: Optional[str] = Field(None, description="type/key text (e.g. 'hello' or 'cmd+c')")
    value: Optional[str] = Field(None, description="set_value text")
    mouse_button: Optional[str] = Field(None, description="click: left|right|middle (default left)")
    click_count: Optional[int] = Field(None, description="click count 1..3")
    scroll_direction: Optional[str] = Field(None, description="scroll: up|down|left|right")
    scroll_amount: Optional[float] = Field(
        None,
        description="scroll amount (default 1); wheel fallback uses 10 wheel notches per unit, 0.1 for fine movement, not a fixed pixel/page distance",
    )
    include_screenshot: bool = Field(False, description="state: attach jpeg screenshot (base64)")
    probe_screen: bool = Field(False, description="status: probe Screen Recording permission")
    repeat: Optional[int] = Field(None, description="key: repeat count 1..50")
    element_action: Optional[str] = Field(
        None, description="action: exact action name from the latest tree (e.g. Press)"
    )


async def _json_dumps_result(data: dict[str, Any]) -> str:
    return await run_long_blocking_io(json.dumps, data, ensure_ascii=False, default=str)


def _build_payload(data: _ComputerUseInput) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    if data.pid is not None:
        payload["pid"] = data.pid
    if data.name:
        payload["name"] = data.name
    if data.window_id is not None:
        payload["window_id"] = data.window_id
    if data.index is not None:
        payload["target"] = {"type": "element", "index": data.index}
    elif data.x is not None and data.y is not None:
        payload["target"] = {"type": "coordinate", "x": data.x, "y": data.y}
    if data.text is not None:
        payload["text"] = data.text
    if data.value is not None:
        payload["value"] = data.value
    if data.mouse_button:
        payload["mouse_button"] = data.mouse_button
    if data.click_count is not None:
        payload["click_count"] = data.click_count
    if data.scroll_direction:
        payload["scroll_direction"] = data.scroll_direction
    if data.scroll_amount is not None:
        payload["scroll_amount"] = data.scroll_amount
    if data.include_screenshot:
        payload["include_screenshot"] = True
    if data.probe_screen:
        payload["probe_screen"] = True
    if data.repeat is not None:
        payload["repeat"] = data.repeat
    if data.url:
        payload["url"] = data.url
    if data.app:
        payload["app"] = data.app
    if data.args:
        payload["args"] = data.args
    if data.element_action:
        payload["action"] = data.element_action
    return payload


async def _format_result(result: dict[str, Any], runtime: Any = None) -> str:
    if not isinstance(result, dict):
        return str(result)
    if "error" in result:
        detail = result.get("detail") or ""
        return f"ERROR {result['error']}" + (f": {detail}" if detail else "")
    screenshot = result.get("screenshot")
    if isinstance(screenshot, dict) and screenshot.get("data_b64"):
        block = {
            "base64": screenshot["data_b64"],
            "mime_type": screenshot.get("mime", "image/jpeg"),
        }
        # Persist privately before the SSE limit; pixels never get an anonymous URL.
        await upload_binary_blocks(
            {"blocks": [block]},
            get_base_url_from_runtime(runtime),
            private=True,
            private_user_id=get_user_id_from_runtime(runtime),
            private_session_id=get_session_id_from_runtime(runtime),
        )
        result = {
            **result,
            "screenshot": {
                **{k: v for k, v in screenshot.items() if k != "data_b64"},
                **{k: v for k, v in block.items() if k in ("url", "upload_error")},
            },
        }
    serialized = await _json_dumps_result(result)
    # Keep the JSON envelope below the SSE parse limit, including screenshot metadata.
    while len(serialized) > 90_000 and isinstance(result.get("state"), str) and result["state"]:
        result = {
            **result,
            "state": result["state"][: len(result["state"]) // 2],
            "truncated": True,
        }
        serialized = await _json_dumps_result(result)
    return serialized


@tool("computer_use", args_schema=_ComputerUseInput)
async def computer_use(
    action: Annotated[
        str,
        "One of: status, apps, launch, windows, state, activate, click, set_value, "
        "type, key, scroll, action",
    ],
    url: Annotated[Optional[str], "launch: URL to open in default browser"] = None,
    app: Annotated[Optional[str], "launch: executable path or macOS .app bundle (no shell)"] = None,
    args: Annotated[Optional[list[str]], "launch: argv for app"] = None,
    machine_id: Annotated[Optional[str], "target a specific registered machine"] = None,
    pid: Annotated[
        Optional[int],
        "Target app pid from apps. Required unless name is supplied for all actions except status/apps/launch.",
    ] = None,
    name: Annotated[Optional[str], "Target app name (exact match)"] = None,
    window_id: Annotated[Optional[int], "Pin one window"] = None,
    index: Annotated[Optional[int], "Element index from latest state"] = None,
    x: Annotated[Optional[float], "Coordinate fallback x"] = None,
    y: Annotated[Optional[float], "Coordinate fallback y"] = None,
    text: Annotated[Optional[str], "Text for type/key"] = None,
    value: Annotated[Optional[str], "Value for set_value"] = None,
    mouse_button: Annotated[Optional[str], "left|right|middle"] = None,
    click_count: Annotated[Optional[int], "Click count 1..3"] = None,
    scroll_direction: Annotated[Optional[str], "up|down|left|right"] = None,
    scroll_amount: Annotated[Optional[float], "Scroll pages"] = None,
    include_screenshot: Annotated[bool, "Attach screenshot to state"] = False,
    probe_screen: Annotated[bool, "Probe Screen Recording in status"] = False,
    repeat: Annotated[Optional[int], "Key repeat count"] = None,
    element_action: Annotated[Optional[str], "action: name from tree actions= (e.g. Press)"] = None,
    runtime: ToolRuntime = None,  # type: ignore[assignment]
) -> str:
    """Operate native apps / the desktop on the user's OWN machine via the local sandbox.

    Availability: requires an online desktop app daemon. With no explicit session
    machine selection the user's default machine is pinned automatically (registry
    default, adopted from the first registered machine). The session's pinned
    machine is authoritative. You cannot change it with tool arguments; ask the
    user to change the session selection instead. If the pinned machine is offline,
    stop instead of selecting another machine. On ``dispatch_failed: offline`` tell
    the user to open LambChat on that machine; do not retry blindly.

    Workflow (always):
    Coordinate clicks also require pid or name; never assume the current app implicitly.
    1. ``launch`` to open a URL or start an app — this is the correct way to start
       browsers/GUI apps (detached, survives; do NOT start GUI apps via shell execute).
    2. ``apps`` to find the pid (``launch.launcher_pid`` may belong to a wrapper,
       not the accessible app; browsers are multi-process: only ONE pid owns windows —
       probe candidates with ``windows`` and keep the pid that returns windows).
    3. ``state`` to observe the accessibility tree. Element indices address the LATEST
       observation; every new ``state`` renumbers. Re-observe after a GUI change before
       using indices again. Read-only status/apps/windows/state calls do not require
       another observation. For truncated trees, use ``state(index=...)`` on a known
       document/container; subtree indices replace the previous ones. Omit index to
       return to the full window. Screenshots still show the verified target window.
    4. Prefer element actions (accessibility press/value work on background apps, no
       focus stealing). Coordinates/keyboard are last resorts and need the app frontmost
       (``foreground_required`` otherwise; the event path NEVER activates apps silently —
       call ``activate`` explicitly first when you truly need keyboard shortcuts).
       ``type`` with an element ``index`` focuses the element and writes the value via
       accessibility (works on background windows); raw ``type``/``key`` without an
       index types into whatever is frontmost.
    5. Multi-window apps: ``windows`` lists them; pin with window_id. Without it the
       key/main window is re-resolved each observation — a just-opened modal becomes the
       captured window (check the ``window:`` header line first when things look wrong).

    If the current tree and screenshot demonstrate the requested outcome,
    finish without more input or identical observations. Re-observe after a change
    or to resolve specific missing evidence, not to repeatedly reconfirm the same state.
    If a repeated observation provides no new evidence, change the approach or report
    the specific uncertainty instead of polling the same state indefinitely.

    Scrolling: target the content region with index or x/y, especially for nested scroll
    areas; a toolbar, sidebar or another pane can consume the wheel. Without a target,
    wheel fallback uses the active window center. Start with scroll_amount=0.1 for fine
    movement or 1 for larger movement; distance depends on the app and OS settings.
    Re-observe to verify movement and adjust; repeated ok results do not prove scrolling.
    At a nested region's boundary, scroll chaining can move its parent. Confirm the last
    item and scrollbar position with state; do not probe a visible boundary with more
    wheel input. If the parent moves, target outside the nested region to restore it.

    Office editors: a selected spreadsheet cell may not support ``set_value``. Activate
    the app, enter cell editing mode (usually F2), then ``type`` and confirm with Enter.
    Use the Name Box or Go To command for exact cell addresses; confirm the selected
    address before editing instead of guessing spreadsheet cell centers from pixels.
    Formatting shortcuts toggle: verify the selected range and current value or format dialog
    before repeating them; do not infer success from font appearance alone.
    In tabbed editors such as WPS, verify the active document tab and cell address before
    typing: a pid alone does not identify a document. If the tab changes, re-select the
    intended file and re-observe before continuing; do not type into another document.
    Close startup dialogs first; re-observe after saving to handle format confirmations.
    Office dialogs can run in a different process (including WPS Go To). If the editor
    loses focus, rediscover with ``apps`` / ``windows`` and use the active dialog's pid
    for ``state``, screenshots and keys instead of keeping the parent editor's pid.
    When ``state.foreground_pid`` is present, observe that pid to identify the active
    dialog before acting; the original observation still belongs to its requested pid.
    File pickers may belong to a separate desktop portal process. If the editor loses
    focus after Save As, use ``apps`` / ``windows`` to find the active dialog and its pid.
    Saved desktop files are on the selected machine, not automatically in the Agent's
    workspace. Fast Agent uses a Store-backed virtual filesystem: an empty ``ls`` there
    does not mean a desktop save failed. Verify through the native app unless a filesystem
    tool is explicitly connected to the same machine and path.

    Browser pages (Chromium family): the page DOM may NOT appear in the tree until the
    browser activates accessibility — if ``state`` shows only window chrome, prefer URL
    navigation instead of trying to click into the page (e.g. open
    ``https://www.baidu.com/s?wd=<query>`` via ``launch`` for searches); address-bar
    and browser chrome (tabs/buttons) are always visible. Firefox exposes page DOM
    more readily. On Linux/Wayland launch browsers with
    ``--ozone-platform=wayland --disable-gpu --force-renderer-accessibility`` plus a
    fresh ``--user-data-dir`` (default X11 mode exits silently without XWayland);
    pass the executable path (e.g. ``/usr/bin/microsoft-edge``) — bare names are
    resolved from PATH.

    Hard rules:
    - NEVER use osascript/AppleScript/System Events/JXA for UI automation — an unattended
      TCC permission dialog hangs forever. This tool is the replacement.
    - For settable elements prefer set_value over typing.
    - ``action`` invokes a named accessibility action: pass ``element_action`` from
      the latest tree's actions= list and the element ``index``.
    - Coordinate targets use global screen coordinates, not cropped screenshot pixels.
      Add the window origin and account for screenshot scaling using window.bounds.
      For scroll, pass an element index or coordinates to target the scroll area.
    - Errors are structured: ax_not_trusted/screen_recording_denied → tell the user to
      grant Accessibility & Screen Recording to LambChat.app once in System Settings
      (macOS) / enable toolkit-accessibility (Linux); app_not_found → ``apps``;
      element_unavailable/stale_state → re-observe with ``state``; offline → see
      Availability above.
    - Screenshots (include_screenshot=true) are attached as images to vision-enabled models.
      Prefer accessibility indices when available; use the screenshot to verify document
      content and locate controls missing from the tree.
    """

    action = (action or "").strip().lower()
    if action not in _ACTIONS:
        return f"ERROR invalid_action: choose one of {', '.join(_ACTIONS)}"
    if action not in ("status", "apps", "launch") and pid is None and not name:
        return "ERROR invalid_arguments: this action needs pid or name"
    if action == "launch" and not url and not app:
        return "ERROR invalid_arguments: launch needs url or app"

    user_id = get_user_id_from_runtime(runtime)
    if not user_id:
        return "ERROR no_user_context"

    config = getattr(runtime, "config", None)
    configurable = config.get("configurable", {}) if isinstance(config, dict) else {}
    selection = configurable.get("computer_use_context")
    if not isinstance(selection, dict):
        return "ERROR machine_selection_required: select an online machine in this session"
    selected_machine = selection.get("machine_id")
    if not isinstance(selected_machine, str) or not selected_machine:
        return "ERROR machine_selection_required: select an online machine in this session"
    if machine_id and machine_id != selected_machine:
        return "ERROR machine_mismatch: tool arguments cannot change the session's selected machine"
    session_id = get_session_id_from_runtime(runtime)
    if not session_id:
        return "ERROR session_required: desktop access requires a trusted session"

    payload = _build_payload(
        _ComputerUseInput(
            action=action,
            pid=pid,
            name=name,
            window_id=window_id,
            index=index,
            x=x,
            y=y,
            text=text,
            value=value,
            mouse_button=mouse_button,
            click_count=click_count,
            scroll_direction=scroll_direction,
            scroll_amount=scroll_amount,
            include_screenshot=include_screenshot,
            probe_screen=probe_screen,
            repeat=repeat,
            url=url,
            app=app,
            args=args,
            element_action=element_action,
        )
    )
    payload["session_id"] = session_id
    async with _desktop_call_lock(user_id, selected_machine):
        policy = await _lookup_confirm_policy(user_id, selected_machine)
        read_only = action in ("status", "apps", "windows") or (
            action == "state" and not include_screenshot
        )
        operation = json.dumps({"action": action, **payload}, sort_keys=True, ensure_ascii=False)
        confirmation_context = {
            "machine_id": selected_machine,
            "operation_sha256": hashlib.sha256(operation.encode()).hexdigest(),
        }
        resumed = selection.get("resume")
        if isinstance(resumed, dict):
            original = resumed.get("confirmation_context") or {}
            same_call = resumed.get("tool_call_id") == getattr(runtime, "tool_call_id", None)
            if original.get("machine_id") != selected_machine or (
                same_call
                and (resumed.get("approved") is not True or original != confirmation_context)
            ):
                return "ERROR declined_by_user: resumed desktop approval no longer matches this operation"
        if not confirm_local_op(
            "computer_use read" if read_only else "rm computer_use operation",
            policy,
            description=f"Computer control on machine {selected_machine}: {operation}"
            + (" (includes a screenshot sent to the model)" if include_screenshot else ""),
            tool_call_id=str(getattr(runtime, "tool_call_id", "") or ""),
            confirmation_context=confirmation_context,
        ):
            return "ERROR declined_by_user: approval missing or operation changed; do not retry without an explicit user request"
        try:
            resp = await dispatch_local_call(
                user_id, f"cua_{action}", payload, machine_id=selected_machine
            )
        except Exception as exc:  # noqa: BLE001 - AppError(SANDBOX_*) 等统一转文本
            # AppError.__str__ retains interpolation placeholders.
            message = exc.display_message if isinstance(exc, AppError) else str(exc)
            logger.warning("[computer_use] dispatch failed action=%s: %s", action, message)
            hint = ""
            if "offline" in message.lower():
                hint = " (local sandbox daemon offline — ask the user to open the LambChat desktop app)"
            return f"ERROR dispatch_failed: {message}{hint}"

        result = resp.get("result") if isinstance(resp, dict) else None
        if result is None:
            error = resp.get("error") if isinstance(resp, dict) else resp
            return f"ERROR daemon_error: {error}"
        if isinstance(result, dict):
            result = {**result, "machine_id": selected_machine}
        return await _format_result(result, runtime)
