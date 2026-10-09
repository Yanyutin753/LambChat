"""PAT 存储与服务端配对。

- 凭据绑定服务器 origin；keyring 使用 origin 索引，本地 JSON marker 必须一致。
- pair() 完成「密码登录 -> 换 PAT -> 本地存储」三步，任何一步失败抛 AuthError。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TypeGuard

import httpx

from lambchat_sandbox import paths
from lambchat_sandbox.config import load_config, server_origin
from lambchat_sandbox.private_files import write_private_bytes

try:  # keyring 为可选依赖，缺失时静默使用文件后端
    import keyring
except ImportError:  # pragma: no cover - 是否触发取决于运行环境
    keyring = None  # type: ignore[assignment]

KEYRING_SERVICE = "lambchat-sandbox"
KEYRING_USER = "pat"


class AuthError(Exception):
    """认证/配对失败；code 携带服务端 detail.code（无则为 "unknown"）。"""

    def __init__(self, message: str, *, code: str = "unknown") -> None:
        super().__init__(message)
        self.code = code


def _origin(server_url: str | None) -> str:
    return server_origin(server_url if server_url is not None else load_config().server_url)


def _write_credential(path: Path, origin: str, token: str | None) -> None:
    write_private_bytes(path, json.dumps({"origin": origin, "token": token}).encode("utf-8"))


def _valid_token(token: object) -> TypeGuard[str]:
    return isinstance(token, str) and bool(token) and all(33 <= ord(char) <= 126 for char in token)


def store_pat(token: str, path: Path | None = None, *, server_url: str | None = None) -> None:
    """Bind the credential to its issuing origin; a marker gates keyring access."""
    if not _valid_token(token):
        raise AuthError("Invalid PAT response", code="invalid_response")
    origin = _origin(server_url)
    p = path if path is not None else paths.pat_file()
    previous = None
    stored_in_keyring = False
    if keyring is not None:
        try:
            previous = keyring.get_password(KEYRING_SERVICE, origin)
            keyring.set_password(KEYRING_SERVICE, origin, token)
            stored_in_keyring = True
        except Exception:
            pass
    try:
        _write_credential(p, origin, None if stored_in_keyring else token)
    except BaseException:
        if stored_in_keyring:
            try:
                if previous is None:
                    keyring.delete_password(KEYRING_SERVICE, origin)
                else:
                    keyring.set_password(KEYRING_SERVICE, origin, previous)
            except Exception:
                pass
        raise


def load_pat(path: Path | None = None, *, server_url: str | None = None) -> str | None:
    """A file credential overrides keyring; unbound or mismatched credentials are refused."""
    origin = _origin(server_url)
    p = path if path is not None else paths.pat_file()
    try:
        credential = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(credential, dict) or credential.get("origin") != origin:
        return None
    token = credential.get("token")
    if _valid_token(token):
        return token
    if "token" not in credential or token is not None:
        return None
    if keyring is not None:
        try:
            token = keyring.get_password(KEYRING_SERVICE, origin)
            return token if _valid_token(token) else None
        except Exception:
            pass
    return None


def clear_pat(path: Path | None = None) -> None:
    """Removing the credential marker also prevents stale keyring tokens from resurfacing."""
    p = path if path is not None else paths.pat_file()
    try:
        credential = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        credential = None
    if keyring is not None:
        users = [KEYRING_USER]
        if isinstance(credential, dict) and isinstance(credential.get("origin"), str):
            users.append(credential["origin"])
        for user in users:
            try:
                keyring.delete_password(KEYRING_SERVICE, user)
            except Exception:
                pass
    try:
        p.unlink()
    except FileNotFoundError:
        pass


async def pair(
    server_url: str,
    username: str,
    password: str,
    *,
    transport: httpx.AsyncBaseTransport | None = None,
    persist: bool = True,
) -> str:
    """密码登录换取 PAT 并存储，返回 PAT 明文。

    transport 参数供测试注入 httpx.MockTransport。
    """
    server_origin(server_url)
    base = server_url.rstrip("/")
    async with httpx.AsyncClient(base_url=base, transport=transport, timeout=15.0) as client:
        login_resp = await client.post(
            "/api/auth/login", json={"username": username, "password": password}
        )
        _raise_for_auth_error(login_resp, "登录失败")
        try:
            payload = login_resp.json()
            access_token = payload.get("access_token") if isinstance(payload, dict) else None
        except ValueError:
            access_token = None
        if not _valid_token(access_token):
            raise AuthError(
                f"登录响应缺少 access_token: HTTP {login_resp.status_code}", code="invalid_response"
            )

        pat_resp = await client.post(
            "/api/auth/pat",
            json={"name": "sandbox-daemon", "scopes": ["sandbox:execute"]},
            headers={"Authorization": f"Bearer {access_token}"},
        )
        _raise_for_auth_error(pat_resp, "创建 PAT 失败")
        try:
            payload = pat_resp.json()
            token = payload.get("token") if isinstance(payload, dict) else None
        except ValueError:
            token = None
        if not _valid_token(token):
            raise AuthError(
                f"PAT 响应缺少 token: HTTP {pat_resp.status_code}", code="invalid_response"
            )

    if persist:
        store_pat(token, server_url=server_url)
    return token


def _raise_for_auth_error(resp: httpx.Response, context: str) -> None:
    """非 2xx 时抛 AuthError，尽量带上服务端 detail.code / detail.message。"""
    if resp.is_success:
        return
    code = "unknown"
    message = f"{context}: HTTP {resp.status_code}"
    try:
        payload = resp.json()
        detail = payload.get("detail") if isinstance(payload, dict) else None
    except ValueError:
        detail = None
    if isinstance(detail, dict):
        code = str(detail.get("code", code))
        server_message = detail.get("message")
        if server_message:
            message = f"{context}: {server_message} (code={code})"
        else:
            message = f"{context}: HTTP {resp.status_code} (code={code})"
    elif isinstance(detail, str) and detail:
        message = f"{context}: {detail}"
    raise AuthError(message, code=code)
