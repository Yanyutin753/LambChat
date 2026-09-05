"""LambChat 本地沙箱客户端配置。"""

from __future__ import annotations

import json
import os
import tempfile
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
    # 壳侧配对回执（Rust save_pairing 落盘）：daemon 目前只回读不使用，
    # 网页端 PAT 管理页可据此对上"哪一条是本机桌面壳"。
    pat_id: str | None = None


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

    raw_pat_id = raw.get("pat_id")
    if raw_pat_id is not None and not isinstance(raw_pat_id, str):  # 壳侧写入；缺键走 None
        raise ConfigError(f"pat_id must be a string or null, got {raw_pat_id!r} ({p})")

    cfg = SandboxConfig(
        server_url=str(raw.get("server_url", SandboxConfig.server_url)),
        data_root=Path(str(raw.get("data_root", SandboxConfig.data_root))),
        confirm_policy=str(raw.get("confirm_policy", SandboxConfig.confirm_policy)),
        embedded_python=raw_embedded,
        pat_id=raw_pat_id,
    )
    _validate(cfg, p)
    return cfg


def save_config(cfg: SandboxConfig, path: Path | None = None) -> None:
    """原子写 JSON（M4 T8）：临时文件落同目录 + ``os.replace`` 原子换位。

    直接对目标文件落笔时进程中途死掉会留下半份 JSON——daemon 下次启动直接
    ConfigError 拒绝服务。临时文件在目标同目录创建（跨文件系统无法
    ``os.replace``）；失败清理半成品，成功后无残留。
    """
    p = path if path is not None else config_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "server_url": cfg.server_url,
        "data_root": str(cfg.data_root),
        "confirm_policy": cfg.confirm_policy,
        "embedded_python": cfg.embedded_python,
    }
    if cfg.pat_id is not None:  # 未设置不落键，保持旧配置文件形态
        payload["pat_id"] = cfg.pat_id
    body = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    fd, tmp_name = tempfile.mkstemp(dir=p.parent, prefix=f".{p.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(body)
        os.replace(tmp_name, p)
    except BaseException:
        os.unlink(tmp_name)
        raise


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
