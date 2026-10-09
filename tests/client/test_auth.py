"""PAT 存储（keyring/文件双后端）与服务端配对 + CLI。"""

import json
import stat

import httpx
import pytest

import lambchat_sandbox.auth as auth
import lambchat_sandbox.cli as cli
import lambchat_sandbox.config as config_mod
from lambchat_sandbox import paths, private_files
from lambchat_sandbox.auth import AuthError, clear_pat, load_pat, pair, store_pat
from lambchat_sandbox.cli import main


@pytest.fixture(autouse=True)
def _isolate_pat_store(monkeypatch, tmp_path):
    """默认强制文件后端 + tmp 根（LAMBCHAT_HOME 注入），不触碰真实 keyring 与 ~/.lambchat。"""
    monkeypatch.setattr(auth, "keyring", None)
    monkeypatch.setenv(paths.HOME_ENV, str(tmp_path))
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
    assert json.loads(p.read_text(encoding="utf-8"))["token"] == "token-1"
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


def test_store_prefers_keyring_when_available(monkeypatch, tmp_path):
    fake = FakeKeyring()
    monkeypatch.setattr(auth, "keyring", fake)
    store_pat("token-4")
    assert fake.store == {(auth.KEYRING_SERVICE, "http://127.0.0.1:8000"): "token-4"}
    assert json.loads((tmp_path / "pat").read_text()) == {
        "origin": "http://127.0.0.1:8000",
        "token": None,
    }
    assert load_pat() == "token-4"


def test_keyring_failure_falls_back_to_file(monkeypatch, tmp_path):
    monkeypatch.setattr(auth, "keyring", FakeKeyring(fail=True))
    store_pat("token-5")
    pat_file = tmp_path / "pat"
    assert json.loads(pat_file.read_text(encoding="utf-8"))["token"] == "token-5"
    assert stat.S_IMODE(pat_file.stat().st_mode) == 0o600
    assert load_pat() == "token-5"  # keyring 读失败回退文件


# ---------- pair 配对 ----------


async def test_pair_success_returns_and_stores_pat():
    log: list[httpx.Request] = []
    token = await pair("https://lc.example", "alice", "s3cret", transport=_transport(log))
    assert token == "pat-plain-token"
    assert load_pat(server_url="https://lc.example") == "pat-plain-token"

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
    monkeypatch.setattr(cli, "load_pat", lambda **kwargs: None)
    assert main(["run"]) == 1
    assert "login" in capsys.readouterr().err


def test_cli_logout_clears_pat(capsys):
    store_pat("token-6")
    assert main(["logout"]) == 0
    assert load_pat() is None


def test_cli_status_without_pat_returns_1(capsys):
    assert main(["status"]) == 1
    assert "login" in capsys.readouterr().err


def test_cli_login_stores_pat_without_printing_any_token(monkeypatch, capsys):
    async def fake_pair(server_url, username, password, **kwargs):
        assert username == "alice"
        assert password == "hunter2"
        return "abcdefghijklmnop"

    monkeypatch.setattr(cli, "pair", fake_pair)
    monkeypatch.setattr("builtins.input", lambda prompt="": "alice")
    monkeypatch.setattr(cli.getpass, "getpass", lambda prompt="": "hunter2")
    assert main(["login"]) == 0
    out = capsys.readouterr().out
    assert "abcdefgh" not in out
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


def test_cli_login_keeps_reverse_proxy_path(monkeypatch, tmp_path):
    async def fake_pair(server_url, username, password, **kwargs):
        assert server_url == "https://lc.example/lambchat"
        return "synthetic-token"

    monkeypatch.setattr(cli, "pair", fake_pair)
    monkeypatch.setattr("builtins.input", lambda prompt="": "alice")
    monkeypatch.setattr(cli.getpass, "getpass", lambda prompt="": "synthetic-password")
    assert main(["login", "--server", "https://lc.example/lambchat/"]) == 0
    assert config_mod.load_config().server_url == "https://lc.example/lambchat"


@pytest.mark.parametrize("local_write_fails", [False, True])
def test_cli_can_repair_legacy_http_pairing_without_losing_identity(
    monkeypatch,
    tmp_path,
    local_write_fails,
):
    p = tmp_path / "sandbox.json"
    original = b'{"server_url":"http://192.168.1.2:8000","machine_id":"fixed-device"}'
    p.write_bytes(original)

    async def fake_pair(server_url, username, password, **kwargs):
        assert server_url == "https://secure.example"
        return "synthetic-pat"

    monkeypatch.setattr(cli, "pair", fake_pair)
    monkeypatch.setattr("builtins.input", lambda prompt="": "alice")
    monkeypatch.setattr(cli.getpass, "getpass", lambda prompt="": "synthetic-password")
    if local_write_fails:

        def fail_store(*args, **kwargs):
            raise OSError("synthetic storage failure")

        monkeypatch.setattr(cli, "store_pat", fail_store)
    assert main(["login", "--server", "https://secure.example"]) == int(local_write_fails)
    if local_write_fails:
        assert p.read_bytes() == original
    else:
        assert config_mod.load_config().server_url == "https://secure.example"
        assert config_mod.load_config().machine_id == "fixed-device"


async def test_pair_sends_credentials_only_to_configured_reverse_proxy_path():
    seen = []

    def handler(request):
        seen.append(str(request.url))
        if request.url.path.endswith("/login"):
            return httpx.Response(200, json={"access_token": "synthetic-access"})
        return httpx.Response(200, json={"token": "synthetic-pat"})

    await pair(
        "https://lc.example/lambchat/",
        "alice",
        "synthetic-password",
        transport=httpx.MockTransport(handler),
        persist=False,
    )
    assert seen == [
        "https://lc.example/lambchat/api/auth/login",
        "https://lc.example/lambchat/api/auth/pat",
    ]


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


# Credentials must remain bound to the origin that issued them.
def test_origin_bound_pat_cannot_be_loaded_for_another_server(tmp_path):
    p = tmp_path / "pat"
    store_pat("synthetic-a", path=p, server_url="https://a.example")
    assert load_pat(path=p, server_url="https://a.example") == "synthetic-a"
    assert load_pat(path=p, server_url="https://b.example") is None


def test_rust_pairing_file_overrides_old_keyring_token(monkeypatch, tmp_path):
    fake = FakeKeyring()
    fake.store[(auth.KEYRING_SERVICE, auth.KEYRING_USER)] = "synthetic-legacy"
    fake.store[(auth.KEYRING_SERVICE, "https://a.example")] = "synthetic-old"
    monkeypatch.setattr(auth, "keyring", fake)
    p = tmp_path / "pat"
    p.write_text(json.dumps({"origin": "https://b.example", "token": "synthetic-rust"}))
    assert load_pat(path=p, server_url="https://b.example") == "synthetic-rust"
    assert load_pat(path=p, server_url="https://a.example") is None


def test_unbound_legacy_credentials_are_never_sent_to_a_configured_origin(monkeypatch, tmp_path):
    fake = FakeKeyring()
    fake.store[(auth.KEYRING_SERVICE, auth.KEYRING_USER)] = "synthetic-legacy"
    monkeypatch.setattr(auth, "keyring", fake)
    p = tmp_path / "pat"
    p.write_text("synthetic-legacy")
    assert load_pat(path=p, server_url="https://new.example") is None
    p.unlink()
    assert load_pat(path=p, server_url="https://new.example") is None


def test_cli_failed_remote_login_does_not_change_config_or_old_credential(monkeypatch, tmp_path):
    config_mod.save_config(
        config_mod.SandboxConfig(
            server_url="https://old.example",
            machine_id="machine-fixed",
            machine_name="workstation",
            pat_id="old-pat",
        )
    )
    original = (tmp_path / "sandbox.json").read_bytes()
    (tmp_path / "pat").write_text("synthetic-existing")

    async def failed_pair(*args, **kwargs):
        raise AuthError("denied")

    monkeypatch.setattr(cli, "pair", failed_pair)
    monkeypatch.setattr("builtins.input", lambda prompt="": "alice")
    monkeypatch.setattr(cli.getpass, "getpass", lambda prompt="": "synthetic-password")
    assert main(["login", "--server", "https://new.example"]) == 1
    assert (tmp_path / "sandbox.json").read_bytes() == original
    assert (tmp_path / "pat").read_text() == "synthetic-existing"


def test_cli_successful_login_preserves_machine_identity_and_does_not_print_token(
    monkeypatch, tmp_path, capsys
):
    config_mod.save_config(
        config_mod.SandboxConfig(
            server_url="https://old.example",
            machine_id="machine-fixed",
            machine_name="workstation",
            pat_id="old-pat",
        )
    )

    async def successful_pair(*args, **kwargs):
        assert kwargs["persist"] is False
        return "synthetic-secret"

    monkeypatch.setattr(cli, "pair", successful_pair)
    monkeypatch.setattr("builtins.input", lambda prompt="": "alice")
    monkeypatch.setattr(cli.getpass, "getpass", lambda prompt="": "synthetic-password")
    assert main(["login", "--server", "https://new.example"]) == 0
    cfg = config_mod.load_config()
    assert cfg.machine_id == "machine-fixed"
    assert cfg.machine_name == "workstation"
    assert cfg.pat_id is None
    assert load_pat(server_url="https://new.example") == "synthetic-secret"
    output = capsys.readouterr().out
    assert "synthetic" not in output


def test_credential_temp_is_private_before_any_secret_is_replaced(monkeypatch, tmp_path):
    import os

    p = tmp_path / "pat"
    original_replace = os.replace
    observed = []

    def inspect_replace(source, destination):
        assert stat.S_IMODE(auth.Path(source).stat().st_mode) == 0o600
        assert json.loads(auth.Path(source).read_text())["origin"] == "https://a.example"
        observed.append(source)
        original_replace(source, destination)

    monkeypatch.setattr(private_files.os, "replace", inspect_replace)
    store_pat("synthetic-private", path=p, server_url="https://a.example")
    assert observed
    assert list(tmp_path.glob(".pat.*.tmp")) == []


def test_failed_credential_replace_keeps_previous_pairing_and_rolls_back_keyring(
    monkeypatch, tmp_path
):
    fake = FakeKeyring()
    monkeypatch.setattr(auth, "keyring", fake)
    p = tmp_path / "pat"
    store_pat("synthetic-old", path=p, server_url="https://a.example")
    original = p.read_bytes()

    def fail_replace(*args):
        raise OSError("synthetic disk failure")

    monkeypatch.setattr(private_files.os, "replace", fail_replace)
    with pytest.raises(OSError):
        store_pat("synthetic-new", path=p, server_url="https://a.example")
    assert p.read_bytes() == original
    assert load_pat(path=p, server_url="https://a.example") == "synthetic-old"
    assert list(tmp_path.glob(".pat.*.tmp")) == []


def test_windows_acl_failure_happens_before_secret_write_and_preserves_previous_file(
    monkeypatch, tmp_path
):
    p = tmp_path / "pat"
    p.write_text(json.dumps({"origin": "https://a.example", "token": "synthetic-old"}))
    original = p.read_bytes()
    seen = []

    def fail_acl(path):
        assert auth.Path(path).read_bytes() == b""
        seen.append(path)
        raise OSError("synthetic ACL failure")

    monkeypatch.setattr(private_files, "_restrict_windows_owner", fail_acl)
    monkeypatch.setattr(private_files, "_IS_WINDOWS", True)
    with pytest.raises(OSError):
        store_pat("synthetic-new", path=p, server_url="https://a.example")
    assert seen
    assert p.read_bytes() == original
    assert list(tmp_path.glob(".pat.*.tmp")) == []


def test_cli_credential_save_failure_restores_previous_config(monkeypatch, tmp_path, capsys):
    config_mod.save_config(
        config_mod.SandboxConfig(
            server_url="https://old.example", machine_id="machine-fixed", machine_name="workstation"
        )
    )
    previous = (tmp_path / "sandbox.json").read_bytes()

    async def successful_pair(*args, **kwargs):
        return "synthetic-secret"

    def fail_store(*args, **kwargs):
        raise OSError("synthetic disk failure")

    monkeypatch.setattr(cli, "pair", successful_pair)
    monkeypatch.setattr(cli, "store_pat", fail_store)
    monkeypatch.setattr("builtins.input", lambda prompt="": "alice")
    monkeypatch.setattr(cli.getpass, "getpass", lambda prompt="": "synthetic-password")
    assert main(["login", "--server", "https://new.example"]) == 1
    assert (tmp_path / "sandbox.json").read_bytes() == previous
    assert "synthetic-secret" not in str(capsys.readouterr())


@pytest.mark.parametrize("command", ["status", "run"])
def test_cli_does_not_connect_using_a_pat_bound_to_another_server(monkeypatch, command, capsys):
    config_mod.save_config(
        config_mod.SandboxConfig(server_url="https://new.example", machine_id="machine-fixed")
    )
    store_pat("synthetic-old", server_url="https://old.example")

    def unexpected_request(*args, **kwargs):
        pytest.fail("credential mismatch must stop before network connection")

    monkeypatch.setattr(cli.httpx, "get", unexpected_request)
    monkeypatch.setattr(cli, "run_daemon", unexpected_request)
    assert main([command]) == 1
    assert "login" in capsys.readouterr().err


def test_windows_acl_command_uses_constant_script_and_environment_path(monkeypatch, tmp_path):
    from unittest.mock import Mock

    run = Mock()
    monkeypatch.setattr(private_files.subprocess, "run", run)
    p = tmp_path / "quote'; $(command)" / "pat"
    private_files._restrict_windows_owner(p)
    args, kwargs = run.call_args
    assert args[0][-1] == private_files._WINDOWS_OWNER_ACL
    assert str(p) not in args[0][-1]
    assert kwargs["env"]["LAMBCHAT_CREDENTIAL_PATH"] == str(p)
    assert kwargs["check"] is True
    assert kwargs["capture_output"] is True


async def test_pair_rejects_unsafe_server_before_sending_password():
    from lambchat_sandbox.config import ConfigError

    calls = []
    with pytest.raises(ConfigError):
        await pair(
            "http://remote.example", "alice", "synthetic-password", transport=_transport(calls)
        )
    assert calls == []


async def test_pair_can_return_valid_token_without_persisting_it():
    token = await pair(
        "https://lc.example", "alice", "synthetic-password", transport=_transport([]), persist=False
    )
    assert token == "pat-plain-token"
    assert not paths.pat_file().exists()


@pytest.mark.parametrize(
    "credential",
    [
        "synthetic-raw",
        {"token": "synthetic-unbound"},
        {"origin": "https://a.example", "token": "bad\nheader"},
        {"origin": "https://a.example", "token": 123},
        {"origin": "https://a.example"},
    ],
)
def test_invalid_credential_envelopes_fail_closed(tmp_path, credential):
    p = tmp_path / "pat"
    p.write_text(json.dumps(credential))
    assert load_pat(path=p, server_url="https://a.example") is None


def test_origin_keyring_markers_cannot_resurrect_after_logout(monkeypatch, tmp_path):
    fake = FakeKeyring()
    monkeypatch.setattr(auth, "keyring", fake)
    store_pat("synthetic-old", server_url="https://a.example")
    assert load_pat(server_url="https://a.example") == "synthetic-old"
    (tmp_path / "pat").unlink()  # Rust logout cannot enumerate Python keyring secrets.
    assert load_pat(server_url="https://a.example") is None


def test_origin_canonicalization_uses_same_keyring_scope(monkeypatch):
    fake = FakeKeyring()
    monkeypatch.setattr(auth, "keyring", fake)
    store_pat("synthetic-current", server_url="https://A.example:443/")
    assert set(fake.store) == {(auth.KEYRING_SERVICE, "https://a.example")}
    assert load_pat(server_url="https://a.example") == "synthetic-current"


@pytest.mark.parametrize("route", ["/api/auth/login", "/api/auth/pat"])
async def test_pair_rejects_nonobject_auth_response_without_persisting_credentials(route):
    def response(request):
        if request.url.path == route:
            return httpx.Response(200, json=["synthetic-response"])
        return httpx.Response(200, json={"access_token": "synthetic-jwt"})

    with pytest.raises(AuthError) as error:
        await pair(
            "https://lc.example",
            "alice",
            "synthetic-password",
            transport=httpx.MockTransport(response),
        )
    assert error.value.code == "invalid_response"
    assert not paths.pat_file().exists()
