#!/usr/bin/env python3
"""云端沙箱「超时暂停 → 无感自动恢复」部署后检验。

验证对象：E2B / CubeSandbox 云端沙箱平台（SANDBOX_PLATFORM=local 时输出 SKIP）。
原理：显式 pause 用户沙箱（与超时暂停同为内存快照机制，无需等真实超时到点），
随后发消息要求读回 pause 前写入的文件——全程应零报错且文件内容原样保留，
即为「无感自愈」（keepalive / 唤醒重试 / connect 自动恢复链路）。

用法（在本机或运维机上跑，通过 kubectl 操作目标集群）：
  # 生产（复用 disttest 用户）：
  python3 scripts/verify_sandbox_pause_heal.py \
      --base-url https://lambchat.com --namespace lambchat --deployment lambchat-a \
      --user-id 6999be7275bdd6b1d868075b
  # staging（一次性注册测试用户，结束自动回收）：
  python3 scripts/verify_sandbox_pause_heal.py \
      --base-url https://test.lambchat.com --namespace lambchat-staging \
      --deployment lambchat-staging --register

输出：人读 ✅/❌ 行 + 末行 RESULT:{"ok":true/false,...}（供 run-all.sh 采集）。
退出码：0 = PASS/SKIP，1 = FAIL。
仅用标准库；不改任何系统配置（超时、平台均保持目标环境现状）。
"""

from __future__ import annotations

import argparse
import json
import secrets
import subprocess
import sys
import time
import urllib.error
import urllib.request
from typing import Any

RUN_TIMEOUT_S = 360
POLL_INTERVAL_S = 10


def http_json(
    url: str,
    *,
    method: str = "GET",
    token: str | None = None,
    body: dict[str, Any] | None = None,
    timeout: int = 30,
) -> Any:
    req = urllib.request.Request(url, method=method)
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    data = None
    if body is not None:
        data = json.dumps(body).encode()
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, data, timeout=timeout) as resp:
            return json.loads(resp.read() or b"{}")
    except urllib.error.HTTPError as e:
        detail = e.read()[:300].decode(errors="replace")
        raise RuntimeError(f"HTTP {e.code} {url}: {detail}") from e


def kubectl_exec(deploy_args: list[str], pod_script: str) -> str:
    """把 python 脚本喂进目标 deployment 的 venv python，返回 stdout。"""
    cmd = [*deploy_args, "--", "/app/.venv/bin/python", "-"]
    proc = subprocess.run(cmd, input=pod_script.encode(), capture_output=True, timeout=180)
    out = proc.stdout.decode(errors="replace").strip()
    if proc.returncode != 0:
        raise RuntimeError(
            f"in-pod helper failed (rc={proc.returncode}): {proc.stderr.decode()[:400]}"
        )
    return out


MINT_SCRIPT = """
import asyncio
async def main():
    from src.infra.auth.jwt import create_access_token
    print(create_access_token({user_id!r}, expires_delta=None))
asyncio.run(main())
"""

PREFLIGHT_SCRIPT = """
import asyncio
async def main():
    from src.kernel.config import settings
    from src.kernel.config.service import initialize_settings
    await initialize_settings()
    print(settings.SANDBOX_PLATFORM)
asyncio.run(main())
"""

PAUSE_SCRIPT = """
import asyncio

async def main():
    from src.kernel.config import settings
    from src.kernel.config.service import initialize_settings
    await initialize_settings()
    if settings.SANDBOX_PLATFORM not in {"e2b", "cubesandbox"}:
        print("SKIP:not-cloud")
        return
    from src.infra.storage.mongodb import get_mongo_client
    client = get_mongo_client()
    doc = await client[settings.MONGODB_DB]["user_sandbox_bindings"].find_one(
        {"user_id": USER_ID}
    )
    sandbox_id = (doc or {}).get("sandbox_id")
    if not sandbox_id:
        print("FAIL:no-binding")
        return
    if settings.SANDBOX_PLATFORM == "e2b":
        from src.infra.sandbox._adapters import E2BSandboxAdapter as Adapter
        adapter = Adapter(api_key=settings.E2B_API_KEY, template=settings.E2B_TEMPLATE,
                          timeout=settings.E2B_TIMEOUT)
    else:
        from src.infra.sandbox._adapters import CubeSandboxAdapter as Adapter
        adapter = Adapter(api_url=settings.CUBE_API_URL, template=settings.CUBE_TEMPLATE,
                          proxy_node_ip=settings.CUBE_PROXY_NODE_IP,
                          proxy_port_http=settings.CUBE_PROXY_PORT_HTTP,
                          sandbox_domain=settings.CUBE_SANDBOX_DOMAIN,
                          timeout=settings.CUBE_TIMEOUT,
                          request_timeout=settings.CUBE_REQUEST_TIMEOUT)
    sandbox = adapter.get_sandbox(sandbox_id)
    if sandbox is None:
        print(f"FAIL:cannot-connect:{sandbox_id}")
        return
    adapter.pause_sandbox(sandbox)
    info = adapter.get_sandbox_info(sandbox)
    state = info.get("state", "unknown")
    if state != "paused":
        print(f"FAIL:pause-state:{state}")
        return
    print(f"OK:{sandbox_id}")

asyncio.run(main())
"""

REGISTER_CLEANUP_SCRIPT = """
import asyncio

async def main():
    from src.kernel.config import settings
    from src.infra.storage.mongodb import get_mongo_client
    client = get_mongo_client()
    db = client[settings.MONGODB_DB]
    user = await db["users"].find_one({"username": USERNAME})
    uid = str(user["_id"]) if user else None
    binding = await db["user_sandbox_bindings"].find_one({"user_id": uid}) if uid else None
    if binding and binding.get("sandbox_id"):
        from src.kernel.config.service import initialize_settings
        await initialize_settings()
        try:
            if settings.SANDBOX_PLATFORM == "e2b":
                from src.infra.sandbox._adapters import E2BSandboxAdapter as Adapter
                adapter = Adapter(api_key=settings.E2B_API_KEY,
                                  template=settings.E2B_TEMPLATE,
                                  timeout=settings.E2B_TIMEOUT)
            else:
                from src.infra.sandbox._adapters import CubeSandboxAdapter as Adapter
                adapter = Adapter(api_url=settings.CUBE_API_URL,
                                  template=settings.CUBE_TEMPLATE,
                                  proxy_node_ip=settings.CUBE_PROXY_NODE_IP,
                                  proxy_port_http=settings.CUBE_PROXY_PORT_HTTP,
                                  sandbox_domain=settings.CUBE_SANDBOX_DOMAIN,
                                  timeout=settings.CUBE_TIMEOUT,
                                  request_timeout=settings.CUBE_REQUEST_TIMEOUT)
            sbx = adapter.get_sandbox(binding["sandbox_id"])
            if sbx is not None:
                adapter.kill_sandbox(sbx)
        except Exception as exc:
            print("sandbox-kill-skipped:", exc)
    if uid:
        for coll in ("user_sandbox_bindings", "sessions", "traces"):
            await db[coll].delete_many({"user_id": uid})
        await db["users"].delete_one({"_id": user["_id"]})
    print("cleaned")

asyncio.run(main())
"""


def wait_run_done(base: str, token: str, session_id: str, run_id: str) -> dict[str, Any]:
    deadline = time.time() + RUN_TIMEOUT_S
    while time.time() < deadline:
        time.sleep(POLL_INTERVAL_S)
        payload = http_json(f"{base}/api/sessions/{session_id}/runs", token=token)
        runs = (
            payload
            if isinstance(payload, list)
            else payload.get("runs") or payload.get("data") or []
        )
        match = next((r for r in runs if r.get("run_id") == run_id), None)
        status = (match or {}).get("status")
        if status in {"completed", "error", "failed", "cancelled"}:
            return match or {"status": status}
    return {"status": "timeout"}


def fetch_run_events(base: str, token: str, session_id: str, run_id: str) -> list[dict[str, Any]]:
    payload = http_json(f"{base}/api/sessions/{session_id}/events", token=token)
    events = (
        payload if isinstance(payload, list) else payload.get("events") or payload.get("data") or []
    )
    return [e for e in events if e.get("run_id") == run_id]


def assert_run_clean(events: list[dict[str, Any]], label: str) -> str:
    problems: list[str] = []
    for e in events:
        etype = e.get("event_type", "")
        data = json.dumps(e.get("data", {}), ensure_ascii=False)
        if etype == "error":
            problems.append(f"error 事件: {data[:160]}")
        if etype == "tool:result" and ("Command failed" in data or "timed out" in data.lower()):
            problems.append(f"工具失败: {data[:160]}")
    if problems:
        raise AssertionError(f"[{label}] " + " | ".join(problems[:4]))
    chunks = [
        e.get("data", {}).get("content", "")
        for e in events
        if e.get("event_type") == "message:chunk"
    ]
    return "".join(chunks)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", required=True, help="如 https://lambchat.com")
    parser.add_argument("--namespace", required=True)
    parser.add_argument("--deployment", required=True)
    parser.add_argument("--kubectl-cmd", default="kubectl")
    parser.add_argument("--user-id", help="复用已有用户（生产 disttest 用户）")
    parser.add_argument(
        "--register", action="store_true", help="注册一次性测试用户（结束自动回收）"
    )
    parser.add_argument("--agent", default="team")
    parser.add_argument("--keep", action="store_true", help="跳过一次性用户回收")
    args = parser.parse_args()

    deploy_args = [
        *args.kubectl_cmd.split(),
        "-n",
        args.namespace,
        "exec",
        "-i",
        f"deploy/{args.deployment}",
    ]
    base = args.base_url.rstrip("/")
    ok = False
    detail = ""
    register_user = None

    try:
        platform = kubectl_exec(deploy_args, PREFLIGHT_SCRIPT)
        print(f"[preflight] SANDBOX_PLATFORM={platform}")
        if platform not in {"e2b", "cubesandbox"}:
            print(f"✅ SKIP  云端沙箱暂停恢复检验仅适用 e2b/cubesandbox（当前 {platform}）")
            print('RESULT:{"ok": true, "skip": true, "reason": "platform=' + platform + '"}')
            return 0

        if args.user_id:
            user_id = args.user_id
            token = kubectl_exec(deploy_args, MINT_SCRIPT.format(user_id=user_id))
        else:
            register_user = f"sbheal-{secrets.token_hex(4)}"
            password = secrets.token_urlsafe(12)
            created = http_json(
                f"{base}/api/auth/register",
                method="POST",
                body={
                    "username": register_user,
                    "email": f"{register_user}@example.com",
                    "password": password,
                },
            )
            user_id = created["user"]["id"]
            kubectl_exec(
                deploy_args,
                "import asyncio\n"
                "async def main():\n"
                "    from src.kernel.config import settings\n"
                "    from src.infra.storage.mongodb import get_mongo_client\n"
                "    client = get_mongo_client()\n"
                "    r = await client[settings.MONGODB_DB]['users'].update_one(\n"
                f"        {{'username': {register_user!r}}},\n"
                "        {'$set': {'is_active': True, 'email_verified': True}})\n"
                "    print('activated' if r.modified_count else 'missing')\n"
                "asyncio.run(main())\n",
            )
            token = http_json(
                f"{base}/api/auth/login",
                method="POST",
                body={"username": register_user, "password": password},
            )["access_token"]
        print(f"[user] user_id={user_id} mode={'register' if register_user else 'mint'}")

        marker = f"SANDBOX-HEAL-{secrets.token_hex(4)}"
        session_id = f"sandbox-heal-probe-{user_id[:8]}"

        # ── 第 1 轮：写入标记文件（同时建立/复用沙箱）──
        r1 = http_json(
            f"{base}/api/chat/stream?agent_id={args.agent}",
            method="POST",
            token=token,
            body={
                "message": (
                    f"在沙箱里执行：echo {marker} > heal-probe.txt && cat heal-probe.txt，"
                    "把输出原样贴给我。若沙箱启动或命令有任何异常，原样告诉我。"
                ),
                "session_id": session_id,
                "max_steps": 30,
            },
        )
        run1 = r1["run_id"]
        state = wait_run_done(base, token, session_id, run1)
        print(f"[round1] status={state.get('status')}")
        if state.get("status") != "completed":
            raise AssertionError(f"round1 未完成: {state}")
        text1 = assert_run_clean(fetch_run_events(base, token, session_id, run1), "round1")
        if marker not in text1:
            raise AssertionError(f"round1 未回显标记（写文件失败?）: {text1[:200]}")
        print(f"✅ PASS  round1 写入+回显标记（{marker}）")

        # ── 显式暂停（与超时暂停同机制：内存快照 pause）──
        pause_out = kubectl_exec(deploy_args, PAUSE_SCRIPT.replace("USER_ID", f"{user_id!r}"))
        print(f"[pause] {pause_out}")
        if not pause_out.startswith("OK:"):
            raise AssertionError(f"暂停失败: {pause_out}")

        # ── 第 2 轮：暂停后读回（验证无感自动恢复 + 快照数据保留）──
        r2 = http_json(
            f"{base}/api/chat/stream?agent_id={args.agent}",
            method="POST",
            token=token,
            body={
                "message": (
                    "执行 cat heal-probe.txt，把内容原样贴给我，并执行 echo resumed-ok。"
                    "如果沙箱需要重新启动或有任何异常，原样告诉我。"
                ),
                "session_id": session_id,
                "max_steps": 30,
            },
        )
        run2 = r2["run_id"]
        state = wait_run_done(base, token, session_id, run2)
        print(f"[round2] status={state.get('status')}")
        if state.get("status") != "completed":
            raise AssertionError(f"round2 未完成: {state}")
        text2 = assert_run_clean(fetch_run_events(base, token, session_id, run2), "round2")
        if marker not in text2:
            raise AssertionError(f"round2 未读回标记（快照数据丢失?）: {text2[:200]}")
        if "resumed-ok" not in text2:
            raise AssertionError(f"round2 未执行 resumed-ok: {text2[:200]}")
        print("✅ PASS  round2 暂停后无感恢复（零报错 + 快照文件完整 + 新命令可执行）")
        ok = True
        detail = "pause→resume seamless, marker intact"
    except Exception as exc:  # noqa: BLE001
        detail = str(exc)[:300]
        print(f"❌ FAIL  {detail}")
    finally:
        if register_user and not args.keep:
            try:
                out = kubectl_exec(
                    deploy_args,
                    REGISTER_CLEANUP_SCRIPT.replace("USERNAME", f"{register_user!r}"),
                )
                print(f"[cleanup] {out}")
            except Exception as exc:  # noqa: BLE001
                print(f"[cleanup] 跳过: {exc}")

    print("RESULT:" + json.dumps({"ok": ok, "detail": detail}, ensure_ascii=False))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
