"""沙箱数据根解析：LAMBCHAT_HOME 优先，缺省 ``~/.lambchat``。

壳（Rust ``sandbox_home()``，frontend/src-tauri/src/daemon.rs）与 daemon
（本模块）两侧读同一个 ``LAMBCHAT_HOME``——迁移沙箱根时两进程解析到同一
目录；未设/空白一律回落 ``~/.lambchat``，既有用户行为不变。

所有子路径一律**调用时**解析（不留模块级常量）：daemon 由壳 spawn 继承
环境，用户级环境变量改动需重启壳生效，但进程内即设即读，测试注入也无
需 import 顺序配合。
"""

from __future__ import annotations

import os
from pathlib import Path

#: 根目录覆盖环境变量名（与 Rust sandbox_home() 同名约定）。
HOME_ENV = "LAMBCHAT_HOME"


def home_root() -> Path:
    """沙箱数据根：LAMBCHAT_HOME 优先（空白视同未设），缺省 ~/.lambchat。"""
    raw = os.environ.get(HOME_ENV, "")
    if raw.strip():
        return Path(raw).expanduser()
    return Path.home() / ".lambchat"


def pat_file() -> Path:
    """PAT 明文回退文件（keyring 不可用时）：{root}/pat。"""
    return home_root() / "pat"


def config_file() -> Path:
    """沙箱配置：{root}/sandbox.json。"""
    return home_root() / "sandbox.json"


def workspaces_root() -> Path:
    """会话工作区默认根（SandboxConfig.data_root 缺省）：{root}/workspaces。"""
    return home_root() / "workspaces"


def audit_root() -> Path:
    """审计 JSONL 目录：{root}/audit。"""
    return home_root() / "audit"


def resources_dir() -> Path:
    """壳播种的 PBS 归档查找目录：{root}/resources/python。"""
    return home_root() / "resources" / "python"


def install_root() -> Path:
    """PBS 解压根：{root}/python/<tag>。"""
    return home_root() / "python"
