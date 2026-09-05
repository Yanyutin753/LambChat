"""LambChat 本地沙箱客户端配置。"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

_VALID_CONFIRM_POLICIES = frozenset({"all", "commands", "none"})


class ConfigError(Exception):
    """配置文件解析或校验失败。"""


@dataclass
class SandboxConfig:
    server_url: str = "http://127.0.0.1:8000"
    data_root: Path = Path.home() / ".lambchat" / "workspaces"
    confirm_policy: str = "all"  # all | commands | none
    embedded_python: bool = True  # 内嵌 PBS 运行时（false 走系统 PATH）


def config_path() -> Path:
    """默认配置文件路径：~/.lambchat/sandbox.json"""
    return Path.home() / ".lambchat" / "sandbox.json"


def load_config(path: Path | None = None) -> SandboxConfig:
    """加载配置；文件不存在时返回默认值，不写盘。"""
    p = path if path is not None else config_path()
    if not p.exists():
        return SandboxConfig()
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ConfigError(f"invalid JSON in {p}: {exc}") from exc
    if not isinstance(raw, dict):
        raise ConfigError(f"config root must be a JSON object: {p}")

    raw_embedded = raw.get("embedded_python", SandboxConfig.embedded_python)
    if not isinstance(raw_embedded, bool):  # 旧配置缺字段走默认；非布尔值拒绝
        raise ConfigError(f"embedded_python must be a boolean, got {raw_embedded!r} ({p})")

    cfg = SandboxConfig(
        server_url=str(raw.get("server_url", SandboxConfig.server_url)),
        data_root=Path(str(raw.get("data_root", SandboxConfig.data_root))),
        confirm_policy=str(raw.get("confirm_policy", SandboxConfig.confirm_policy)),
        embedded_python=raw_embedded,
    )
    _validate(cfg, p)
    return cfg


def save_config(cfg: SandboxConfig, path: Path | None = None) -> None:
    """写 JSON（mkdir -p 父目录）。"""
    p = path if path is not None else config_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "server_url": cfg.server_url,
        "data_root": str(cfg.data_root),
        "confirm_policy": cfg.confirm_policy,
        "embedded_python": cfg.embedded_python,
    }
    p.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _validate(cfg: SandboxConfig, source: Path) -> None:
    if cfg.confirm_policy not in _VALID_CONFIRM_POLICIES:
        raise ConfigError(
            f"confirm_policy must be one of {sorted(_VALID_CONFIRM_POLICIES)}, "
            f"got {cfg.confirm_policy!r} ({source})"
        )
    if not (cfg.server_url.startswith("http://") or cfg.server_url.startswith("https://")):
        raise ConfigError(
            f"server_url must start with http:// or https://, got {cfg.server_url!r} ({source})"
        )
