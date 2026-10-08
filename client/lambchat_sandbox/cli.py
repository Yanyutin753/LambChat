"""lambchat_sandbox 命令行入口：login / logout / status / run / version / update。"""

from __future__ import annotations

import argparse
import asyncio
import getpass
import json
import os
import sys
import tempfile
from dataclasses import replace

import httpx

from lambchat_sandbox import __version__, selfupdate
from lambchat_sandbox.auth import AuthError, clear_pat, load_pat, pair, store_pat
from lambchat_sandbox.config import (
    ConfigError,
    config_path,
    load_config,
    save_config,
    server_origin,
)
from lambchat_sandbox.daemon import run_daemon
from lambchat_sandbox.selfupdate import SelfUpdateError
from lambchat_sandbox.transport import TransportAuthError, UpdateRequiredError


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="lambchat_sandbox", description="LambChat 本地沙箱客户端")
    sub = parser.add_subparsers(dest="command", required=True)

    login_p = sub.add_parser("login", help="与服务端配对：登录并创建 PAT")
    login_p.add_argument("--server", default=None, help="覆盖配置中的 server_url 并保存")

    sub.add_parser("logout", help="清除本地 PAT")
    sub.add_parser("status", help="查询服务端沙箱状态")
    sub.add_parser("run", help="启动沙箱 daemon：连接服务端通道并在本机受控执行命令")
    sub.add_parser("version", help="打印客户端版本")
    update_p = sub.add_parser("update", help="自更新：检查 GitHub latest release 并替换自身二进制")
    update_p.add_argument(
        "--repo", default=None, help="覆盖默认 GitHub 仓库（owner/name，默认 Yanyutin753/LambChat）"
    )
    return parser


def cmd_login(args: argparse.Namespace) -> int:
    cfg = load_config(server_url_override=args.server)
    candidate = args.server or cfg.server_url
    server_origin(candidate)
    cfg = replace(cfg, server_url=candidate.rstrip("/"), pat_id=None)

    username = input("用户名: ").strip()
    if not username:
        print("用户名不能为空", file=sys.stderr)
        return 1
    password = getpass.getpass("密码: ")

    try:
        token = asyncio.run(pair(cfg.server_url, username, password, persist=False))
        p = config_path()
        p.parent.mkdir(parents=True, exist_ok=True)
        backup = None
        if p.exists():
            with tempfile.NamedTemporaryFile(dir=p.parent, delete=False) as snapshot:
                snapshot.write(p.read_bytes())
                backup = snapshot.name
        try:
            save_config(cfg)
            store_pat(token, server_url=cfg.server_url)
        except BaseException:
            if backup is not None:
                os.replace(backup, p)
            else:
                p.unlink(missing_ok=True)
            raise
        finally:
            if backup is not None:
                try:
                    os.unlink(backup)
                except FileNotFoundError:
                    pass
    except AuthError as exc:
        print(f"登录失败: {exc}", file=sys.stderr)
        return 1
    except httpx.HTTPError as exc:
        print(f"无法连接服务端: {exc}", file=sys.stderr)
        return 1
    except OSError:
        print("无法保存配对凭据，请检查本地文件权限", file=sys.stderr)
        return 1

    print("配对成功：凭据已存储")
    return 0


def cmd_logout(args: argparse.Namespace) -> int:
    clear_pat()
    print("已清除本地 PAT")
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    cfg = load_config()
    token = load_pat(server_url=cfg.server_url)
    if not token:
        print("未找到 PAT，请先 lambchat_sandbox login", file=sys.stderr)
        return 1
    try:
        resp = httpx.get(
            f"{cfg.server_url.rstrip('/')}/api/sandbox/status",
            headers={"Authorization": f"Bearer {token}"},
            timeout=15.0,
        )
    except httpx.HTTPError as exc:
        print(f"无法连接服务端: {exc}", file=sys.stderr)
        return 1
    if resp.status_code in (401, 403):
        print("PAT 已失效，请重新 login", file=sys.stderr)
        return 1
    if not resp.is_success:
        print(f"查询失败: HTTP {resp.status_code}", file=sys.stderr)
        return 1
    print(json.dumps(resp.json(), ensure_ascii=False, indent=2))
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    cfg = load_config()
    pat = load_pat(server_url=cfg.server_url)
    if not pat:
        print("未找到 PAT，请先 lambchat_sandbox login", file=sys.stderr)
        return 1
    try:
        asyncio.run(run_daemon(cfg, pat=pat))
    except TransportAuthError as exc:
        print(f"PAT 已失效（{exc}），请重新 lambchat_sandbox login", file=sys.stderr)
        return 1
    except UpdateRequiredError:
        # 版本过低：daemon 主循环已打印升级指引（lambchat_sandbox update），
        # 这里只保证停机退出码非零，不重复刷屏
        return 1
    except (KeyboardInterrupt, asyncio.CancelledError):
        # SIGINT→KeyboardInterrupt、SIGTERM→CancelledError，殊途同归：
        # run_daemon 的 finally 已完成 post_offline + close + 审计 shutdown
        print("[sandbox] 收到中断，已优雅下线")
        return 0
    return 0


def cmd_version(args: argparse.Namespace) -> int:
    print(__version__)
    return 0


def cmd_update(args: argparse.Namespace) -> int:
    try:
        message = selfupdate.perform_update(args.repo or selfupdate.DEFAULT_REPO)
    except SelfUpdateError as exc:
        print(f"更新失败: {exc}", file=sys.stderr)
        return 1
    except httpx.HTTPError as exc:
        print(f"无法连接 GitHub: {exc}", file=sys.stderr)
        return 1
    print(message)
    return 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    handlers = {
        "login": cmd_login,
        "logout": cmd_logout,
        "status": cmd_status,
        "run": cmd_run,
        "version": cmd_version,
        "update": cmd_update,
    }
    try:
        return handlers[args.command](args)
    except ConfigError as exc:
        # 坏配置友好输出（M4 T8）：stderr 一行提示 + 退出码 1，不吐 traceback
        print(f"配置错误: {exc}", file=sys.stderr)
        return 1
