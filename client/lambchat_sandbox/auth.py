"""PAT 存储与服务端配对。

- keyring 可用时优先 keyring；任何失败静默回退到 0600 权限的本地文件。
- pair() 完成「密码登录 -> 换 PAT -> 本地存储」三步，任何一步失败抛 AuthError。
"""

from __future__ import annotations

import os
from pathlib import Path

import httpx

try:  # keyring 为可选依赖，缺失时静默使用文件后端
    import keyring
except ImportError:  # pragma: no cover - 是否触发取决于运行环境
    keyring = None  # type: ignore[assignment]

KEYRING_SERVICE = "lambchat-sandbox"
KEYRING_USER = "pat"

PAT_FILE = Path.home() / ".lambchat" / "pat"


class AuthError(Exception):
    """认证/配对失败；code 携带服务端 detail.code（无则为 "unknown"）。"""

    def __init__(self, message: str, *, code: str = "unknown") -> None:
        super().__init__(message)
        self.code = code


def store_pat(token: str, path: Path | None = None) -> None:
    """存储 PAT：keyring 优先，失败静默写 0600 文件。"""
    if keyring is not None:
        try:
            keyring.set_password(KEYRING_SERVICE, KEYRING_USER, token)
            return
        except Exception:
            pass  # 静默落文件
    p = path if path is not None else PAT_FILE
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(token, encoding="utf-8")
    os.chmod(p, 0o600)


def load_pat(path: Path | None = None) -> str | None:
    """读取 PAT：keyring 优先，取不到回退文件；都没有返回 None。"""
    if keyring is not None:
        try:
            token = keyring.get_password(KEYRING_SERVICE, KEYRING_USER)
            if token:
                return token
        except Exception:
            pass
    p = path if path is not None else PAT_FILE
    try:
        token = p.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        return None
    return token or None


def clear_pat(path: Path | None = None) -> None:
    """清除 PAT：keyring 与文件都尝试删除（后端可能曾发生过回退）。"""
    if keyring is not None:
        try:
            keyring.delete_password(KEYRING_SERVICE, KEYRING_USER)
        except Exception:
            pass
    p = path if path is not None else PAT_FILE
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
) -> str:
    """密码登录换取 PAT 并存储，返回 PAT 明文。

    transport 参数供测试注入 httpx.MockTransport。
    """
    base = server_url.rstrip("/")
    async with httpx.AsyncClient(base_url=base, transport=transport, timeout=15.0) as client:
        login_resp = await client.post(
            "/api/auth/login", json={"username": username, "password": password}
        )
        _raise_for_auth_error(login_resp, "登录失败")
        try:
            access_token = login_resp.json().get("access_token")
        except ValueError:
            access_token = None
        if not access_token:
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
            token = pat_resp.json().get("token")
        except ValueError:
            token = None
        if not token:
            raise AuthError(
                f"PAT 响应缺少 token: HTTP {pat_resp.status_code}", code="invalid_response"
            )

    store_pat(token)
    return token


def _raise_for_auth_error(resp: httpx.Response, context: str) -> None:
    """非 2xx 时抛 AuthError，尽量带上服务端 detail.code / detail.message。"""
    if resp.is_success:
        return
    code = "unknown"
    message = f"{context}: HTTP {resp.status_code}"
    try:
        detail = resp.json().get("detail")
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
