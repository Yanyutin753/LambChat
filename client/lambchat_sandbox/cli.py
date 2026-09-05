"""lambchat_sandbox 命令行入口：login / logout / status / run / version / update。"""

from __future__ import annotations

import argparse
import asyncio
import getpass
import json
import sys

import httpx

from lambchat_sandbox import __version__, selfupdate
from lambchat_sandbox.auth import AuthError, clear_pat, load_pat, pair
from lambchat_sandbox.config import (
    ConfigError,
    SandboxConfig,
    load_config,
    save_config,
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
    cfg = load_config()
    if args.server:
        if not (args.server.startswith("http://") or args.server.startswith("https://")):
            print("server_url 必须以 http:// 或 https:// 开头", file=sys.stderr)
            return 1
        cfg = SandboxConfig(
            server_url=args.server,
            data_root=cfg.data_root,
            confirm_policy=cfg.confirm_policy,
            embedded_python=cfg.embedded_python,
        )
        save_config(cfg)
        print(f"已保存 server_url: {args.server}")

    username = input("用户名: ").strip()
    if not username:
        print("用户名不能为空", file=sys.stderr)
        return 1
    password = getpass.getpass("密码: ")

    try:
        token = asyncio.run(pair(cfg.server_url, username, password))
    except AuthError as exc:
        print(f"登录失败: {exc}", file=sys.stderr)
        return 1
    except httpx.HTTPError as exc:
        print(f"无法连接服务端: {exc}", file=sys.stderr)
        return 1

    print(f"配对成功：PAT {token[:8]}… 已存储")
    return 0


def cmd_logout(args: argparse.Namespace) -> int:
    clear_pat()
    print("已清除本地 PAT")
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    token = load_pat()
    if not token:
        print("未找到 PAT，请先 lambchat_sandbox login", file=sys.stderr)
        return 1
    cfg = load_config()
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
    pat = load_pat()
    if not pat:
        print("未找到 PAT，请先 lambchat_sandbox login", file=sys.stderr)
        return 1
    cfg = load_config()
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
