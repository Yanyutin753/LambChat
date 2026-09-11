"""paths.home_root() 与各子路径解析：LAMBCHAT_HOME 优先、缺省 ~/.lambchat。

壳（Rust sandbox_home()）与 daemon（本模块）两侧读同一个 LAMBCHAT_HOME，
迁移沙箱根时两进程必须解析到同一目录；未设/空白一律回落 ~/.lambchat，
既有用户行为逐字节不变。
"""

from pathlib import Path

from lambchat_sandbox import paths


def test_home_root_defaults_to_home_lambchat(monkeypatch):
    monkeypatch.delenv(paths.HOME_ENV, raising=False)
    assert paths.home_root() == Path.home() / ".lambchat"


def test_home_root_prefers_lambchat_home_env(monkeypatch, tmp_path):
    monkeypatch.setenv(paths.HOME_ENV, str(tmp_path))
    assert paths.home_root() == tmp_path


def test_home_root_blank_env_falls_back_to_home(monkeypatch):
    monkeypatch.setenv(paths.HOME_ENV, "   ")
    assert paths.home_root() == Path.home() / ".lambchat"


def test_subpath_helpers_follow_env_root(monkeypatch, tmp_path):
    monkeypatch.setenv(paths.HOME_ENV, str(tmp_path))
    assert paths.pat_file() == tmp_path / "pat"
    assert paths.config_file() == tmp_path / "sandbox.json"
    assert paths.workspaces_root() == tmp_path / "workspaces"
    assert paths.audit_root() == tmp_path / "audit"
    assert paths.resources_dir() == tmp_path / "resources" / "python"
    assert paths.install_root() == tmp_path / "python"


def test_sandbox_config_defaults_follow_env_root(monkeypatch, tmp_path):
    """data_root 缺省与 config_path 走调用时解析——env 即设即生效。"""
    from lambchat_sandbox.config import SandboxConfig, config_path

    monkeypatch.setenv(paths.HOME_ENV, str(tmp_path))
    assert SandboxConfig().data_root == tmp_path / "workspaces"
    assert config_path() == tmp_path / "sandbox.json"


def test_pbs_ensure_runtime_default_resources_follow_env_root(monkeypatch, tmp_path, capsys):
    """未显式传参时 ensure_runtime 到 LAMBCHAT_HOME 根下找归档。"""
    from lambchat_sandbox import pbs

    monkeypatch.setenv(paths.HOME_ENV, str(tmp_path))
    assert pbs.ensure_runtime() is None
    err = capsys.readouterr().err
    assert str(tmp_path / "resources" / "python" / pbs.TARBALL_NAME) in err


def test_auth_pat_file_follows_env_root(monkeypatch, tmp_path):
    """auth 文件后端经 paths.pat_file() 解析（env 注入即迁移）。"""
    from lambchat_sandbox import auth

    monkeypatch.setattr(auth, "keyring", None)
    monkeypatch.setenv(paths.HOME_ENV, str(tmp_path))
    auth.store_pat("token-x")
    assert (tmp_path / "pat").read_text(encoding="utf-8") == "token-x"
    assert auth.load_pat() == "token-x"
    auth.clear_pat()
    assert not (tmp_path / "pat").exists()
