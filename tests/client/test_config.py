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


def test_save_is_atomic_and_leaves_no_temp_files(tmp_path):
    """原子写（M4 T8）：写盘走临时文件 + os.replace——覆盖既有配置时读者
    永远只看到完整旧版或完整新版，且落定后目录里无临时残留。"""
    p = tmp_path / "sandbox.json"
    save_config(SandboxConfig(server_url="https://first"), p)
    save_config(SandboxConfig(server_url="https://second", pat_id="pat-1"), p)

    data = json.loads(p.read_text())
    assert data["server_url"] == "https://second"
    assert data["pat_id"] == "pat-1"
    leftovers = [f for f in tmp_path.iterdir() if f.name != "sandbox.json"]
    assert leftovers == [], f"save_config 留下临时文件: {leftovers}"


def test_save_config_replaces_existing_file_content_fully(tmp_path):
    """旧配置有未来字段/更长内容：替换后无旧内容残留（truncate 语义）。"""
    p = tmp_path / "sandbox.json"
    p.write_text(json.dumps({"server_url": "https://old", "future_field": "x" * 500}))
    save_config(SandboxConfig(server_url="https://new"), p)
    raw = p.read_text()
    assert "future_field" not in raw
    assert json.loads(raw)["server_url"] == "https://new"


def test_save_config_writes_atomically_source_guard():
    """原子写结构（M4 T8）：save_config 必须走临时文件 + os.replace——直接
    write_text 目标文件时进程中途死掉会留下半份 JSON，daemon 下次启动直接
    ConfigError 拒绝服务。结构断言锁实现形态（行为无法确定性模拟半写崩溃）。"""
    from pathlib import Path

    import lambchat_sandbox.config as config_module

    src = Path(config_module.__file__).read_text(encoding="utf-8")
    body = src.split("def save_config", 1)[1].split("\ndef ", 1)[0]
    assert "os.replace" in body, "save_config 必须用 os.replace 原子落位"
    assert "mkstemp" in body, "临时文件必须在目标同目录创建（同文件系统才可 replace）"
    assert "write_text" not in body, "save_config 不得直接 write_text 目标文件"


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


# ---------- pat_id（M4 T7：壳侧配对回执，daemon 回读用） ----------


def test_pat_id_defaults_none():
    assert SandboxConfig().pat_id is None


def test_load_legacy_config_without_pat_id_stays_none(tmp_path):
    """旧配置缺字段 → None（向后兼容，Rust 写入的 pat_id 不影响旧 daemon 语义）。"""
    p = tmp_path / "sandbox.json"
    p.write_text(json.dumps({"server_url": "http://127.0.0.1:8000", "confirm_policy": "none"}))
    assert load_config(p).pat_id is None


def test_load_reads_pat_id_written_by_shell(tmp_path):
    """壳侧 Rust save_pairing 落盘的 pat_id 可被 daemon 回读。"""
    p = tmp_path / "sandbox.json"
    p.write_text(
        json.dumps(
            {"server_url": "http://127.0.0.1:8000", "confirm_policy": "all", "pat_id": "abc123"}
        )
    )
    assert load_config(p).pat_id == "abc123"


def test_save_roundtrip_keeps_pat_id(tmp_path):
    p = tmp_path / "sandbox.json"
    cfg = SandboxConfig(pat_id="abc123")
    save_config(cfg, p)
    raw = json.loads(p.read_text())
    assert raw["pat_id"] == "abc123"
    assert load_config(p).pat_id == "abc123"


def test_save_omits_pat_id_when_unset(tmp_path):
    """未设置时不写键：保持旧配置文件形态，避免 None 落盘。"""
    p = tmp_path / "sandbox.json"
    save_config(SandboxConfig(), p)
    assert "pat_id" not in json.loads(p.read_text())
