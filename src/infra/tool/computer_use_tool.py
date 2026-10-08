"""computer_use 工具：经本地沙箱 daemon 驱动用户 Mac 的图形界面。

复刻 ZCode computer-use 的语义契约：Accessibility 树优先的观察与操作、
元素索引寻址最近一次观察、事件兜底要求前台。**禁止 osascript / System
Events / AppleScript**——无人值守场景下 TCC 弹窗无人可点会永久卡死。

链路：agent 工具 → 本地 relay(dispatch_local_call)→ daemon cua_ops。
云端沙箱（e2b/daytona/cubesandbox）无此能力，daemon 不在线时报
offline 错误（模型可引导用户启动桌面端）。
"""

from __future__ import annotations

import json
from typing import Annotated, Any, Optional

from langchain.tools import ToolRuntime, tool
from pydantic import BaseModel, Field

from src.infra.agent.events.binary_uploads import upload_binary_blocks
from src.infra.async_utils import run_long_blocking_io
from src.infra.logging import get_logger
from src.infra.sandbox.relay.dispatch import dispatch_local_call
from src.infra.tool.backend_utils import get_user_id_from_runtime

logger = get_logger(__name__)

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
    app: Optional[str] = Field(None, description="launch: executable path to start (no shell)")
    args: Optional[list[str]] = Field(None, description="launch: argv for app")
    machine_id: Optional[str] = Field(
        None, description="target a specific registered machine (multi-machine users)"
    )
    pid: Optional[int] = Field(None, description="target app pid (from apps; preferred over name)")
    name: Optional[str] = Field(None, description="target app name (exact, from apps)")
    window_id: Optional[int] = Field(None, description="pin one window (from windows)")
    index: Optional[int] = Field(
        None, description="element index from the latest state of this app"
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
    scroll_amount: Optional[float] = Field(None, description="scroll pages (default 1)")
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


async def _format_result(result: dict[str, Any]) -> str:
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
        # Store pixels before the SSE text limit; send the same file proxy URL as MCP images.
        await upload_binary_blocks({"blocks": [block]}, "")
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
    app: Annotated[Optional[str], "launch: executable path (no shell)"] = None,
    args: Annotated[Optional[list[str]], "launch: argv for app"] = None,
    machine_id: Annotated[Optional[str], "target a specific registered machine"] = None,
    pid: Annotated[Optional[int], "Target app pid (preferred)"] = None,
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

    Availability: requires the LOCAL sandbox platform (desktop app daemon). Cloud sandbox
    sessions do not have it — on ``dispatch_failed: offline`` tell the user to open the
    LambChat desktop app (or switch the session sandbox to local); do not retry blindly.
    Multi-machine users: pass ``machine_id`` to target a specific registered machine.

    Workflow (always):
    1. ``launch`` to open a URL or start an app — this is the correct way to start
       browsers/GUI apps (detached, survives; do NOT start GUI apps via shell execute).
    2. ``apps`` to find the pid (browsers are multi-process: only ONE pid owns windows —
       probe candidates with ``windows`` and keep the pid that returns windows).
    3. ``state`` to observe the accessibility tree. Element indices address the LATEST
       observation; every new ``state`` renumbers. Re-observe after ANY action before
       acting again (indices from an older observation are invalid → stale_state).
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
    - Screenshot (include_screenshot=true) returns base64 for the human/UI; the
      accessibility tree text is your primary view.
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
    try:
        resp = await dispatch_local_call(user_id, f"cua_{action}", payload, machine_id=machine_id)
    except Exception as exc:  # noqa: BLE001 - AppError(SANDBOX_*) 等统一转文本
        # AppError.__str__ 返回未插值模板("... {{detail}}")——真实原因在
        # args 里,必须走 display_message,否则 daemon 侧错误全被吞成模板
        message = getattr(exc, "display_message", None) or str(exc)
        logger.warning("[computer_use] dispatch failed action=%s: %s", action, message)
        hint = ""
        if "offline" in message.lower():
            hint = " (local sandbox daemon offline — ask the user to open the LambChat desktop app)"
        return f"ERROR dispatch_failed: {message}{hint}"

    result = resp.get("result") if isinstance(resp, dict) else None
    if result is None:
        error = resp.get("error") if isinstance(resp, dict) else resp
        return f"ERROR daemon_error: {error}"
    return await _format_result(result)
