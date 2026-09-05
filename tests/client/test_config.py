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


# ---------- embedded_python（M4 T4：内嵌 PBS 运行时开关） ----------


def test_embedded_python_defaults_true():
    assert SandboxConfig().embedded_python is True


def test_load_missing_file_keeps_embedded_python_default(tmp_path):
    assert load_config(tmp_path / "sandbox.json").embedded_python is True


def test_load_legacy_config_without_embedded_python_field_stays_true(tmp_path):
    """旧配置缺字段 → 默认 True（向后兼容，不因升级翻回系统 PATH）。"""
    p = tmp_path / "sandbox.json"
    p.write_text(json.dumps({"server_url": "http://127.0.0.1:8000", "confirm_policy": "none"}))
    assert load_config(p).embedded_python is True


def test_embedded_python_false_roundtrip(tmp_path):
    p = tmp_path / "sandbox.json"
    save_config(SandboxConfig(embedded_python=False), p)
    assert json.loads(p.read_text())["embedded_python"] is False
    assert load_config(p).embedded_python is False


def test_load_non_bool_embedded_python_rejected(tmp_path):
    p = tmp_path / "sandbox.json"
    p.write_text(json.dumps({"embedded_python": "yes"}))
    with pytest.raises(ConfigError):
        load_config(p)
