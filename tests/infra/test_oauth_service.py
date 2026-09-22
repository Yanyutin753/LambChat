from __future__ import annotations

import asyncio
import base64
import builtins
import importlib
import json
import sys


def test_oauth_module_import_does_not_eagerly_load_authlib(monkeypatch) -> None:
    module_name = "src.infra.auth.oauth"
    sys.modules.pop(module_name, None)

    authlib_imports: list[str] = []
    original_import = builtins.__import__

    def _import(name, globals=None, locals=None, fromlist=(), level=0):
        if name.startswith("authlib"):
            authlib_imports.append(name)
        return original_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", _import)

    oauth_module = importlib.import_module(module_name)

    assert oauth_module.OAuthService is not None
    assert authlib_imports == []


def test_apple_client_secret_is_generated_from_private_key_settings(monkeypatch) -> None:
    from src.infra.auth import oauth as oauth_module

    captured: dict[str, object] = {}

    def fake_encode(payload, key, algorithm=None, headers=None):
        captured["payload"] = payload
        captured["key"] = key
        captured["algorithm"] = algorithm
        captured["headers"] = headers
        return "apple-client-secret.jwt"

    monkeypatch.setattr(oauth_module.jwt, "encode", fake_encode)
    monkeypatch.setattr(oauth_module.settings, "OAUTH_APPLE_TEAM_ID", "TEAM123")
    monkeypatch.setattr(oauth_module.settings, "OAUTH_APPLE_KEY_ID", "KEY123")
    monkeypatch.setattr(oauth_module.settings, "OAUTH_APPLE_CLIENT_ID", "com.example.web")
    monkeypatch.setattr(
        oauth_module.settings,
        "OAUTH_APPLE_CLIENT_SECRET",
        "-----BEGIN PRIVATE KEY-----\\nkey\\n-----END PRIVATE KEY-----",
    )

    secret = oauth_module._build_apple_client_secret()

    assert secret == "apple-client-secret.jwt"
    assert captured["key"] == "-----BEGIN PRIVATE KEY-----\nkey\n-----END PRIVATE KEY-----"
    assert captured["algorithm"] == "ES256"
    assert captured["headers"] == {"kid": "KEY123"}
    assert captured["payload"]["iss"] == "TEAM123"
    assert captured["payload"]["sub"] == "com.example.web"
    assert captured["payload"]["aud"] == "https://appleid.apple.com"


async def test_oauth_service_closes_cached_clients() -> None:
    from src.infra.auth.oauth import OAuthService

    class _FakeClient:
        def __init__(self) -> None:
            self.close_calls = 0

        async def aclose(self) -> None:
            self.close_calls += 1

    service = OAuthService()
    google_client = _FakeClient()
    apple_client = _FakeClient()
    service._oauth_clients = {
        "google": google_client,
        "apple": apple_client,
    }

    await service.close()

    assert google_client.close_calls == 1
    assert apple_client.close_calls == 1
    assert service._oauth_clients == {}


async def test_oauth_service_awaits_future_returned_by_client_close() -> None:
    from src.infra.auth.oauth import OAuthService

    class _FutureCloseClient:
        def __init__(self) -> None:
            self.close_future: asyncio.Future[None] = asyncio.get_running_loop().create_future()

        def aclose(self) -> asyncio.Future[None]:
            asyncio.get_running_loop().call_later(0.01, self.close_future.set_result, None)
            return self.close_future

    service = OAuthService()
    client = _FutureCloseClient()
    service._oauth_clients = {"google": client}

    await service.close()

    assert client.close_future.done() is True
    assert service._oauth_clients == {}


async def test_close_oauth_service_closes_existing_singleton_without_creating_one() -> None:
    from src.infra.auth import oauth as oauth_module
    from src.infra.auth.oauth import OAuthService

    class _FakeClient:
        def __init__(self) -> None:
            self.close_calls = 0

        async def aclose(self) -> None:
            self.close_calls += 1

    oauth_module._oauth_service = None

    await oauth_module.close_oauth_service()

    assert oauth_module._oauth_service is None

    service = OAuthService()
    client = _FakeClient()
    service._oauth_clients = {"google": client}
    oauth_module._oauth_service = service

    await oauth_module.close_oauth_service()

    assert client.close_calls == 1
    assert service._oauth_clients == {}
    assert oauth_module._oauth_service is None


async def test_apple_user_info_offloads_token_header_decode(monkeypatch) -> None:
    from src.infra.auth import oauth as oauth_module
    from src.infra.auth.oauth import OAuthService

    calls: list[str] = []
    header = base64.urlsafe_b64encode(json.dumps({"kid": "kid-1"}).encode()).decode().rstrip("=")
    id_token = f"{header}.payload.signature"

    class _FakeJwksResponse:
        def json(self):
            return {"keys": [{"kid": "kid-1", "kty": "RSA"}]}

    class _FakeAsyncClient:
        def __init__(self, **_kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def get(self, url: str):
            assert url == "https://appleid.apple.com/auth/keys"
            return _FakeJwksResponse()

    def fake_decode(_id_token: str, _jwk: dict, _client_id: str) -> dict:
        return {"sub": "apple-user-1", "email": "apple@example.com"}

    async def fake_run_long_blocking_io(func, *args, **kwargs):
        calls.append(getattr(func, "__name__", ""))
        return func(*args, **kwargs)

    monkeypatch.setattr(oauth_module.httpx, "AsyncClient", _FakeAsyncClient)
    monkeypatch.setattr(oauth_module, "_decode_apple_identity_token", fake_decode)
    monkeypatch.setattr(oauth_module, "run_long_blocking_io", fake_run_long_blocking_io)
    monkeypatch.setattr(oauth_module.settings, "OAUTH_APPLE_CLIENT_ID", "com.example.web")

    user_info = await OAuthService()._get_apple_user_info({"id_token": id_token})

    assert calls == ["_decode_apple_token_header", "fake_decode"]
    assert user_info is not None
    assert user_info.email == "apple@example.com"


async def test_github_user_info_returns_none_when_email_payload_is_not_a_list(
    monkeypatch,
) -> None:
    from src.infra.auth import oauth as oauth_module
    from src.infra.auth.oauth import OAuthService

    class _FakeResponse:
        def __init__(self, payload):
            self._payload = payload

        def json(self):
            return self._payload

    class _FakeAsyncClient:
        def __init__(self, **_kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def get(self, url: str, headers: dict[str, str]):
            if url == "https://api.github.com/user":
                return _FakeResponse({"id": 123, "login": "octo", "email": None})
            if url == "https://api.github.com/user/emails":
                return _FakeResponse({"message": "API rate limit exceeded"})
            raise AssertionError(f"Unexpected URL: {url}")

    monkeypatch.setattr(oauth_module.httpx, "AsyncClient", _FakeAsyncClient)

    user_info = await OAuthService()._get_github_user_info({"access_token": "gho_token"})

    assert user_info is None


async def test_github_user_info_retries_transient_email_payload_error(
    monkeypatch,
) -> None:
    from src.infra.auth import oauth as oauth_module
    from src.infra.auth.oauth import OAuthService

    class _FakeResponse:
        def __init__(self, payload):
            self._payload = payload

        def json(self):
            return self._payload

    class _FakeAsyncClient:
        def __init__(self, **_kwargs):
            self.email_calls = 0

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def get(self, url: str, headers: dict[str, str]):
            if url == "https://api.github.com/user":
                return _FakeResponse({"id": 123, "login": "octo", "email": None})
            if url == "https://api.github.com/user/emails":
                self.email_calls += 1
                if self.email_calls == 1:
                    return _FakeResponse({"message": "Server Error"})
                return _FakeResponse(
                    [
                        {
                            "email": "octo@example.com",
                            "primary": True,
                            "verified": True,
                        }
                    ]
                )
            raise AssertionError(f"Unexpected URL: {url}")

    monkeypatch.setattr(oauth_module.httpx, "AsyncClient", _FakeAsyncClient)

    user_info = await OAuthService()._get_github_user_info({"access_token": "gho_token"})

    assert user_info is not None
    assert user_info.email == "octo@example.com"
