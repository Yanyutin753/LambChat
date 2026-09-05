"""SandboxConfig 加载/保存/校验。"""

import json

import pytest

from lambchat_sandbox.config import ConfigError, SandboxConfig, load_config, save_config


def test_load_missing_returns_default(tmp_path):
    cfg = load_config(tmp_path / "sandbox.json")
    assert cfg.server_url == "http://127.0.0.1:8000"
    assert cfg.confirm_policy == "all"


def test_save_then_load_roundtrip(tmp_path):
    p = tmp_path / "nested" / "sandbox.json"
    save_config(SandboxConfig(server_url="https://lc.example", confirm_policy="none"), p)
    assert json.loads(p.read_text())["server_url"] == "https://lc.example"
    assert load_config(p).confirm_policy == "none"


def test_load_invalid_confirm_policy_rejected(tmp_path):
    p = tmp_path / "sandbox.json"
    p.write_text(json.dumps({"confirm_policy": "yolo"}))
    with pytest.raises(ConfigError):
        load_config(p)


def test_load_broken_json_raises(tmp_path):
    p = tmp_path / "sandbox.json"
    p.write_text("{not json")
    with pytest.raises(ConfigError):
        load_config(p)
