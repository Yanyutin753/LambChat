"""微信 iLink Bot 协议层。

协议对齐 zcode 开源实现（Apache-2.0，packages/services/src/bots/providers/
weixinProvider.ts 与 weixinRegistration.ts）：

- 端点前缀 ``https://ilinkai.weixin.qq.com/ilink/bot``；
- 认证头 ``AuthorizationType: ilink_bot_token`` + ``Authorization: Bearer``，
  附随机 ``X-WECHAT-UIN``（base64(uint32)）；
- 请求体统一包 ``base_info: {channel_version: "2.0.0"}``；
- 响应 ``ret``/``errcode`` 非 0 视为失败（errmsg/message）；
- 收消息 ``/getupdates`` 长轮询（90s），``get_updates_buf`` 为服务端游标；
- 发消息 ``/sendmessage``：文本放 ``msg.item_list`` 的 ``text_item``，
  换行统一 CRLF，``message_type=2``（bot）``message_state=2``（完成）；
- 扫码注册：``GET /get_bot_qrcode?bot_type=3`` → 轮询 ``GET /get_qrcode_status``。
"""

from __future__ import annotations

import base64
import random
import uuid
from typing import Any

import httpx

from src.infra.logging import get_logger

logger = get_logger(__name__)

ILINK_BASE_URL = "https://ilinkai.weixin.qq.com"
BOT_API_PREFIX = "/ilink/bot"
CHANNEL_VERSION = "2.0.0"
MESSAGE_TYPE_BOT = 2
MESSAGE_STATE_FINISH = 2
GET_UPDATES_TIMEOUT_SECONDS = 90.0
REGISTER_TIMEOUT_SECONDS = 30.0
QR_POLL_INTERVAL_SECONDS = 3
QR_EXPIRE_SECONDS = 120

_client: httpx.AsyncClient | None = None


async def get_client() -> httpx.AsyncClient:
    """模块级共享 client（注册轮询与渠道发送复用连接池）。"""
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.AsyncClient(timeout=httpx.Timeout(30.0))
    return _client


async def close_client() -> None:
    global _client
    if _client is not None and not _client.is_closed:
        await _client.aclose()
    _client = None


def build_request_headers(token: str) -> dict[str, str]:
    """iLink 认证头；X-WECHAT-UIN 按协议要求携带随机 uin。"""
    uin = base64.b64encode(str(random.randint(0, 2**32 - 1)).encode()).decode()
    return {
        "content-type": "application/json",
        "AuthorizationType": "ilink_bot_token",
        "Authorization": f"Bearer {token}",
        "X-WECHAT-UIN": uin,
    }


async def _request(
    client: httpx.AsyncClient,
    token: str,
    path: str,
    body: dict[str, Any] | None = None,
    timeout: float = 30.0,
) -> dict[str, Any]:
    payload: dict[str, Any] = {"base_info": {"channel_version": CHANNEL_VERSION}}
    if body:
        payload.update(body)
    response = await client.post(
        f"{ILINK_BASE_URL}{BOT_API_PREFIX}{path}",
        json=payload,
        headers=build_request_headers(token),
        timeout=timeout,
    )
    if response.is_error:
        raise RuntimeError(f"weixin ilink {path} failed: HTTP {response.status_code}")
    try:
        data = response.json()
    except Exception as e:
        raise RuntimeError(f"weixin ilink {path} returned non-JSON body: {e}") from e
    if not isinstance(data, dict):
        raise RuntimeError(f"weixin ilink {path} returned unexpected payload")
    ret = data.get("ret")
    errcode = data.get("errcode")
    if (ret is not None and ret != 0) or (errcode is not None and errcode != 0):
        message = data.get("errmsg") or data.get("message") or f"ret={ret} errcode={errcode}"
        raise RuntimeError(f"weixin ilink {path} failed: {message}")
    return data


def _read_str(record: dict[str, Any] | None, key: str) -> str:
    if not record:
        return ""
    value = record.get(key)
    return value if isinstance(value, str) else ""


def _read_message_text(message: dict[str, Any]) -> str:
    inner = message.get("msg") if isinstance(message.get("msg"), dict) else None
    item_list = message.get("item_list")
    if not isinstance(item_list, list) and isinstance(inner, dict):
        item_list = inner.get("item_list")
    lines: list[str] = []
    if isinstance(item_list, list):
        for item in item_list:
            if not isinstance(item, dict):
                continue
            text_item = item.get("text_item")
            text = _read_str(text_item if isinstance(text_item, dict) else None, "text")
            text = text or _read_str(item, "text") or _read_str(item, "content")
            if text:
                lines.append(text)
    return "\n".join(lines) or _read_str(inner, "text") or _read_str(inner, "content")


def _parse_inbound_message(message: dict[str, Any]) -> dict[str, Any] | None:
    # message_type==2 是 bot 自己发出的消息，跳过防回环
    if message.get("message_type") == MESSAGE_TYPE_BOT:
        return None
    inner = message.get("msg") if isinstance(message.get("msg"), dict) else None

    def _find(key: str) -> str:
        return _read_str(message, key) or _read_str(inner, key)

    sender_id = _find("from_user_id") or _find("from_user") or _find("from") or _find("user")
    if not sender_id:
        # from 可能是嵌套对象 {"id": ...}
        for holder in (message.get("from"), (inner or {}).get("from")):
            if isinstance(holder, dict) and _read_str(holder, "id"):
                sender_id = _read_str(holder, "id")
                break
    content = _read_message_text(message).strip()
    if not sender_id or not content:
        return None
    room = _find("room") or _find("room_id") or _find("chat_id")
    message_id = (
        _find("id") or _find("msgid") or _find("message_id") or str(message.get("id") or "")
    )
    return {
        "sender_id": sender_id,
        "chat_id": room or sender_id,  # 群聊目标为 room，私聊回落发送者
        "content": content,
        "context_token": _find("context_token") or None,
        "message_id": message_id or None,
        "display_name": _find("name") or _find("nickname") or None,
    }


def _next_buf(payload: dict[str, Any]) -> str | None:
    data = payload.get("data") if isinstance(payload.get("data"), dict) else payload
    for key in ("get_updates_buf", "buf", "next_buf", "nextBuf", "syncKey"):
        value = _read_str(data, key)
        if value:
            return value
    return None


def _raw_messages(payload: dict[str, Any]) -> list[dict[str, Any]]:
    data_value = payload.get("data")
    data: dict[str, Any] = data_value if isinstance(data_value, dict) else payload
    raw = None
    for key in ("msgs", "messages", "updates", "items", "list"):
        value = data.get(key)
        if isinstance(value, list):
            raw = value
            break
        if isinstance(value, dict):
            raw = [value]
            break
    return [item for item in (raw or []) if isinstance(item, dict)]


async def get_updates(
    client: httpx.AsyncClient, token: str, buf: str
) -> tuple[list[dict[str, Any]], str | None]:
    """长轮询拉取新消息，返回 (入站消息列表, 下一游标)。"""
    payload = await _request(
        client,
        token,
        "/getupdates",
        body={"get_updates_buf": buf or ""},
        timeout=GET_UPDATES_TIMEOUT_SECONDS,
    )
    messages: list[dict[str, Any]] = []
    for raw in _raw_messages(payload):
        parsed = _parse_inbound_message(raw)
        if parsed is not None:
            messages.append(parsed)
    return messages, _next_buf(payload)


async def send_bot_message(
    client: httpx.AsyncClient,
    token: str,
    *,
    to_user_id: str,
    text: str,
    context_token: str | None = None,
) -> bool:
    """发送文本消息；换行统一 CRLF（微信客户端对 LF 折叠不一致）。"""
    if not to_user_id or not text.strip():
        return False
    normalized = text.replace("\r\n", "\n").replace("\r", "\n").replace("\n", "\r\n")
    msg: dict[str, Any] = {
        "to_user_id": to_user_id,
        "client_id": f"lambchat-weixin-{uuid.uuid4()}",
        "message_type": MESSAGE_TYPE_BOT,
        "message_state": MESSAGE_STATE_FINISH,
        "item_list": [{"type": 1, "text_item": {"text": normalized}}],
    }
    if context_token:
        msg["context_token"] = context_token
    try:
        await _request(client, token, "/sendmessage", body={"msg": msg})
    except RuntimeError as e:
        logger.warning("weixin sendmessage failed: %s", e)
        return False
    return True


async def verify_token(client: httpx.AsyncClient, token: str) -> bool:
    """getconfig 探活，token 有效返回 True。"""
    try:
        await _request(client, token, "/getconfig")
    except RuntimeError as e:
        logger.warning("weixin getconfig failed: %s", e)
        return False
    return True


# ── 扫码注册（GET 端点，无认证） ────────────────────────────────────────────


async def _register_get(client: httpx.AsyncClient, path: str) -> dict[str, Any]:
    response = await client.get(
        f"{ILINK_BASE_URL}{BOT_API_PREFIX}{path}",
        headers={"iLink-App-ClientVersion": "1"},
        timeout=REGISTER_TIMEOUT_SECONDS,
    )
    if response.is_error:
        raise RuntimeError(f"weixin register {path} failed: HTTP {response.status_code}")
    payload = response.json()
    if not isinstance(payload, dict):
        raise RuntimeError("weixin register returned unexpected payload")
    data = payload.get("data")
    merged = {**payload, **(data if isinstance(data, dict) else {})}
    ret, errcode = merged.get("ret"), merged.get("errcode")
    if (ret is not None and ret != 0) or (errcode is not None and errcode != 0):
        message = merged.get("errmsg") or f"ret={ret} errcode={errcode}"
        raise RuntimeError(f"weixin register {path} failed: {message}")
    return merged


def _normalize_qr_status(status: Any) -> str:
    if isinstance(status, bool):
        return "success" if status else "pending"
    if isinstance(status, (int, float)):
        mapping = {0: "pending", 1: "scanned", 2: "success", 3: "expired", 4: "expired"}
        return mapping.get(int(status), "pending")
    if not isinstance(status, str):
        return "pending"
    normalized = status.lower()
    if normalized in {"confirmed", "confirm", "authorized", "success", "ok"}:
        return "success"
    if normalized in {"scaned", "scanned", "scan", "confirmed_wait"}:
        return "scanned"
    if normalized in {"expired", "timeout", "cancel", "cancelled", "canceled"}:
        return "expired"
    if normalized in {"error", "failed", "fail"}:
        return "error"
    return "pending"


async def begin_qr_registration(client: httpx.AsyncClient) -> dict[str, Any]:
    """发起扫码登录，返回 {qr_code, qr_url, expires_in, interval}。"""
    payload = await _register_get(client, "/get_bot_qrcode?bot_type=3")
    qr_code = _read_str(payload, "qrcode") or _read_str(payload, "qr_code")
    qr_url = _read_str(payload, "qrcode_img_content") or _read_str(payload, "qrcode_url") or qr_code
    if not qr_code or not qr_url:
        raise RuntimeError("weixin login did not return a QR code")
    return {
        "qr_code": qr_code,
        "qr_url": qr_url,
        "expires_in": payload.get("expires_in") or QR_EXPIRE_SECONDS,
        "interval": QR_POLL_INTERVAL_SECONDS,
    }


async def poll_qr_registration(client: httpx.AsyncClient, qr_code: str) -> dict[str, Any]:
    """轮询扫码状态：pending/scanned/success(带 bot_token)/expired/error。"""
    from urllib.parse import quote

    try:
        payload = await _register_get(client, f"/get_qrcode_status?qrcode={quote(qr_code)}")
    except httpx.TimeoutException:
        # 状态接口可能长挂等待手机端确认，超时≠失败
        return {"status": "pending", "interval": QR_POLL_INTERVAL_SECONDS}
    status = _normalize_qr_status(
        payload.get("status", payload.get("qrcode_status", payload.get("qr_status")))
    )
    if status == "success":
        bot_token = _read_str(payload, "bot_token") or _read_str(payload, "token")
        if not bot_token:
            return {"status": "error", "message": "login succeeded but no bot_token"}
        return {"status": "success", "bot_token": bot_token}
    return {"status": status, "interval": QR_POLL_INTERVAL_SECONDS}
