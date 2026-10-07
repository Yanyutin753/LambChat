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

from src.infra.async_utils import run_long_blocking_io
from src.infra.logging import get_logger
from src.infra.sandbox.relay.dispatch import dispatch_local_call
from src.infra.tool.backend_utils import get_user_id_from_runtime

logger = get_logger(__name__)

_ACTIONS = (
    "status",
    "apps",
    "windows",
    "state",
    "click",
    "set_value",
    "type",
    "key",
    "scroll",
    "action",
)


class _ComputerUseInput(BaseModel):
    action: str = Field(
        ..., description="status|apps|windows|state|click|set_value|type|key|scroll|action"
    )
    pid: Optional[int] = Field(None, description="target app pid (from apps; preferred over name)")
    name: Optional[str] = Field(None, description="target app name (exact, from apps)")
    window_id: Optional[int] = Field(None, description="pin one window (from windows)")
    index: Optional[int] = Field(
        None, description="element index from the latest state of this app"
    )
    x: Optional[float] = Field(None, description="coordinate fallback: x on the current raster")
    y: Optional[float] = Field(None, description="coordinate fallback: y on the current raster")
    text: Optional[str] = Field(None, description="type/key text (e.g. 'hello' or 'cmd+c')")
    value: Optional[str] = Field(None, description="set_value text")
    mouse_button: Optional[str] = Field(None, description="click: left|right|middle (default left)")
    click_count: Optional[int] = Field(None, description="click count 1..3")
    scroll_direction: Optional[str] = Field(None, description="scroll: up|down|left|right")
    scroll_amount: Optional[float] = Field(None, description="scroll pages (default 1)")
    include_screenshot: bool = Field(False, description="state: attach jpeg screenshot (base64)")
    probe_screen: bool = Field(False, description="status: probe Screen Recording permission")
    repeat: Optional[int] = Field(None, description="key: repeat count 1..50")


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
    return payload


def _format_result(action: str, result: dict[str, Any]) -> str:
    if not isinstance(result, dict):
        return str(result)
    if "error" in result:
        detail = result.get("detail") or ""
        return f"ERROR {result['error']}" + (f": {detail}" if detail else "")
    if action in ("state",):
        return str(result.get("state") or result)
    if action == "apps":
        lines = []
        for app in result.get("apps", []):
            marker = " [active]" if app.get("active") else ""
            lines.append(f"pid={app['pid']} {app['name']}{marker}")
        return "\n".join(lines) or "no apps"
    if action == "windows":
        lines = []
        for index, win in enumerate(result.get("windows", [])):
            flags = ("main" if win.get("main") else "") + (" focused" if win.get("focused") else "")
            lines.append(
                f"[{index}] id={win.get('window_id')} title={win.get('title')!r}"
                + (f" ({flags.strip()})" if flags.strip() else "")
            )
        return "\n".join(lines) or "no windows"
    if action == "status":
        return str(result)
    return str(result)


@tool("computer_use", args_schema=_ComputerUseInput)
async def computer_use(
    action: Annotated[
        str, "One of: status, apps, windows, state, click, set_value, type, key, scroll, action"
    ],
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
    runtime: ToolRuntime = None,  # type: ignore[assignment]
) -> str:
    """Operate the UI of native apps on the user's Mac via the local sandbox daemon.

    Workflow (always):
    1. ``apps`` to find the pid (name match is fallback; copy names character-for-character).
    2. ``state`` to observe the AX tree of the app's window. Element indices address the
       LATEST observation; a new ``state`` renumbers everything.
    3. Act by element index (``click``/``set_value``/``type``/``key``/``scroll``/``action``),
       then ``state`` again to confirm — an accepted action is not proof the app acted.
    4. Prefer element actions (AXPress/AXValue work on background apps, no focus stealing).
       Coordinates and keyboard events are last resorts and require the app to be
       frontmost (``foreground_required`` otherwise; the event path NEVER activates apps).
    5. Multi-window apps: ``windows`` lists them; pin with window_id. Without it the
       key/main window is re-resolved each observation — a just-opened modal becomes the
       captured window (check the ``window:`` header line).

    Hard rules:
    - NEVER use osascript/AppleScript/System Events/JXA for UI automation — an unattended
      TCC permission dialog hangs forever. This tool is the replacement.
    - For settable elements prefer set_value over typing.
    - Errors are structured: ax_not_trusted/screen_recording_denied → tell the user to
      grant Accessibility & Screen Recording to LambChat.app once in System Settings;
      app_not_found → ``apps``; element_unavailable/stale_state → re-observe with ``state``.
    - Screenshot (include_screenshot=true) returns base64 for the human/UI; the AX tree
      text is your primary view.
    """

    action = (action or "").strip().lower()
    if action not in _ACTIONS:
        return f"ERROR invalid_action: choose one of {', '.join(_ACTIONS)}"
    if action not in ("status", "apps") and pid is None and not name:
        return "ERROR invalid_arguments: this action needs pid or name"

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
        )
    )
    try:
        resp = await dispatch_local_call(user_id, f"cua_{action}", payload)
    except Exception as exc:  # noqa: BLE001 - AppError(SANDBOX_*) 等统一转文本
        message = str(exc)
        logger.warning("[computer_use] dispatch failed action=%s: %s", action, message)
        hint = ""
        if "offline" in message.lower():
            hint = " (local sandbox daemon offline — ask the user to open the LambChat desktop app)"
        return f"ERROR dispatch_failed: {message}{hint}"

    result = resp.get("result") if isinstance(resp, dict) else None
    if result is None:
        error = resp.get("error") if isinstance(resp, dict) else resp
        return f"ERROR daemon_error: {error}"
    return _format_result(action, result)
