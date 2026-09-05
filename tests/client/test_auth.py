"""PAT 存储（keyring/文件双后端）与服务端配对 + CLI。"""

import json
import stat

import httpx
import pytest

import lambchat_sandbox.auth as auth
import lambchat_sandbox.cli as cli
import lambchat_sandbox.config as config_mod
from lambchat_sandbox.auth import AuthError, clear_pat, load_pat, pair, store_pat
from lambchat_sandbox.cli import main


@pytest.fixture(autouse=True)
def _isolate_pat_store(monkeypatch, tmp_path):
    """默认强制文件后端 + tmp 路径，不触碰真实 keyring 与 ~/.lambchat。"""
    monkeypatch.setattr(auth, "keyring", None)
    monkeypatch.setattr(auth, "PAT_FILE", tmp_path / "pat")
    monkeypatch.setattr(config_mod, "config_path", lambda: tmp_path / "sandbox.json")


class FakeKeyring:
    """记录调用的最小 keyring 替身。"""

    def __init__(self, fail: bool = False) -> None:
        self.store: dict[tuple[str, str], str] = {}
        self.fail = fail

    def set_password(self, service: str, user: str, value: str) -> None:
        if self.fail:
            raise RuntimeError("keyring backend unavailable")
        self.store[(service, user)] = value

    def get_password(self, service: str, user: str) -> str | None:
        if self.fail:
            raise RuntimeError("keyring backend unavailable")
        return self.store.get((service, user))

    def delete_password(self, service: str, user: str) -> None:
        if self.fail:
            raise RuntimeError("keyring backend unavailable")
        self.store.pop((service, user), None)


def _transport(
    log: list[httpx.Request],
    *,
    login_status: int = 200,
    login_json: dict | None = None,
    pat_status: int = 200,
    pat_json: dict | None = None,
) -> httpx.MockTransport:
    """假造 login/pat 两跳的服务端；记录收到的请求供断言。"""

    def handler(request: httpx.Request) -> httpx.Response:
        log.append(request)
        if request.url.path == "/api/auth/login":
            if login_status >= 400:
                return httpx.Response(login_status, json=login_json)
            return httpx.Response(200, json={"access_token": "jwt-abc"})
        if request.url.path == "/api/auth/pat":
            if pat_status >= 400:
                return httpx.Response(pat_status, json=pat_json)
            return httpx.Response(200, json={"token": "pat-plain-token", "pat_id": "pat-1"})
        return httpx.Response(
            404, json={"detail": {"code": "not_found", "message": "unknown route"}}
        )

    return httpx.MockTransport(handler)


# ---------- 存储三函数 ----------


def test_store_then_load_roundtrip(tmp_path):
    p = tmp_path / "pat"
    store_pat("token-1", path=p)
    assert p.read_text(encoding="utf-8") == "token-1"
    assert load_pat(path=p) == "token-1"


def test_store_creates_parent_dirs_and_chmod_600(tmp_path):
    p = tmp_path / ".lambchat" / "pat"
    store_pat("token-2", path=p)
    assert p.exists()
    assert stat.S_IMODE(p.stat().st_mode) == 0o600


def test_load_missing_returns_none(tmp_path):
    assert load_pat(path=tmp_path / "pat") is None


def test_clear_removes_stored_pat(tmp_path):
    p = tmp_path / "pat"
    store_pat("token-3", path=p)
    clear_pat(path=p)
    assert not p.exists()
    assert load_pat(path=p) is None


def test_clear_missing_pat_is_noop(tmp_path):
    clear_pat(path=tmp_path / "pat")  # 不应抛异常


def test_store_prefers_keyring_when_available(monkeypatch):
    fake = FakeKeyring()
    monkeypatch.setattr(auth, "keyring", fake)
    store_pat("token-4")
    assert fake.store == {(auth.KEYRING_SERVICE, auth.KEYRING_USER): "token-4"}
    assert not auth.PAT_FILE.exists()  # keyring 成功时不落文件
    assert load_pat() == "token-4"


def test_keyring_failure_falls_back_to_file(monkeypatch):
    monkeypatch.setattr(auth, "keyring", FakeKeyring(fail=True))
    store_pat("token-5")
    assert auth.PAT_FILE.read_text(encoding="utf-8") == "token-5"
    assert stat.S_IMODE(auth.PAT_FILE.stat().st_mode) == 0o600
    assert load_pat() == "token-5"  # keyring 读失败回退文件


# ---------- pair 配对 ----------


async def test_pair_success_returns_and_stores_pat():
    log: list[httpx.Request] = []
    token = await pair("https://lc.example", "alice", "s3cret", transport=_transport(log))
    assert token == "pat-plain-token"
    assert load_pat() == "pat-plain-token"

    login_req, pat_req = log
    assert json.loads(login_req.content) == {"username": "alice", "password": "s3cret"}
    assert pat_req.headers["Authorization"] == "Bearer jwt-abc"
    assert json.loads(pat_req.content) == {"name": "sandbox-daemon", "scopes": ["sandbox:execute"]}


async def test_pair_invalid_credentials_raises_auth_error_with_code():
    log: list[httpx.Request] = []
    transport = _transport(
        log,
        login_status=401,
        login_json={
            "detail": {"code": "invalid_credentials", "message": "用户名或密码错误", "args": {}}
        },
    )
    with pytest.raises(AuthError) as excinfo:
        await pair("https://lc.example", "alice", "wrong", transport=transport)
    assert excinfo.value.code == "invalid_credentials"
    assert "invalid_credentials" in str(excinfo.value)
    assert len(log) == 1  # 登录失败后不应发起 PAT 创建
    assert load_pat() is None


async def test_pair_pat_creation_failure_raises_auth_error():
    log: list[httpx.Request] = []
    transport = _transport(
        log,
        pat_status=403,
        pat_json={"detail": {"code": "insufficient_scope", "message": "scope denied", "args": {}}},
    )
    with pytest.raises(AuthError) as excinfo:
        await pair("https://lc.example", "alice", "s3cret", transport=transport)
    assert excinfo.value.code == "insufficient_scope"
    assert len(log) == 2
    assert load_pat() is None  # 失败不落盘


# ---------- CLI ----------


def test_cli_run_without_pat_returns_1(capsys, monkeypatch):
    # run 已接 daemon：无 PAT 时拒绝启动（占位行为已被 T6 取代）
    monkeypatch.setattr(cli, "load_pat", lambda: None)
    assert main(["run"]) == 1
    assert "login" in capsys.readouterr().err


def test_cli_logout_clears_pat(capsys):
    store_pat("token-6")
    assert main(["logout"]) == 0
    assert load_pat() is None


def test_cli_status_without_pat_returns_1(capsys):
    assert main(["status"]) == 1
    assert "login" in capsys.readouterr().err


def test_cli_login_stores_pat_and_prints_prefix_only(monkeypatch, capsys):
    async def fake_pair(server_url, username, password, **kwargs):
        assert username == "alice"
        assert password == "hunter2"
        return "abcdefghijklmnop"

    monkeypatch.setattr(cli, "pair", fake_pair)
    monkeypatch.setattr("builtins.input", lambda prompt="": "alice")
    monkeypatch.setattr(cli.getpass, "getpass", lambda prompt="": "hunter2")
    assert main(["login"]) == 0
    out = capsys.readouterr().out
    assert "abcdefgh" in out  # 前 8 位
    assert "abcdefghijklmnop" not in out  # 完整 PAT 不外泄
    assert "已存储" in out


def test_cli_login_server_override_saved(monkeypatch, tmp_path, capsys):
    async def fake_pair(server_url, username, password, **kwargs):
        assert server_url == "https://lc.example"
        return "qrstuvwxyz1234"

    monkeypatch.setattr(cli, "pair", fake_pair)
    monkeypatch.setattr("builtins.input", lambda prompt="": "alice")
    monkeypatch.setattr(cli.getpass, "getpass", lambda prompt="": "pw")
    assert main(["login", "--server", "https://lc.example"]) == 0
    saved = json.loads((tmp_path / "sandbox.json").read_text(encoding="utf-8"))
    assert saved["server_url"] == "https://lc.example"


def test_cli_login_rejects_bad_server_scheme(monkeypatch, capsys):
    called: list[str] = []

    async def fake_pair(server_url, username, password, **kwargs):
        called.append(server_url)
        return "xxxxxxxxxxxxxxxx"

    monkeypatch.setattr(cli, "pair", fake_pair)
    monkeypatch.setattr("builtins.input", lambda prompt="": "alice")
    monkeypatch.setattr(cli.getpass, "getpass", lambda prompt="": "pw")
    assert main(["login", "--server", "ftp://bad"]) == 1
    assert called == []
