#!/usr/bin/env python3
"""云端沙箱「跨会话共用 + 暂停交织」部署后检验。

同一用户开两个会话，中间穿插显式 pause（与超时暂停同为内存快照机制），
验证：会话隔离（B 看不到 A 的私有文件）、跨会话共享目录可读、
回到 A 文件完整、绑定沙箱 ID 全程不变（恢复而非静默重建）。
是 verify_sandbox_pause_heal.py 的跨对话补充。

用法（在可 kubectl 目标集群的机器上跑）：
  python3 scripts/verify_sandbox_cross_session.py \
      --base-url https://lambchat.com --namespace lambchat \
      --deployment lambchat-a --user-id <uid>

输出：人读 ✅/❌ 行 + 末行 RESULT:{"ok":true/false,...}（供 run-all.sh 采集）。
退出码：0 = PASS，1 = FAIL。仅标准库；local 平台请先用
verify_sandbox_pause_heal.py 的 preflight 判断（本脚本假定云端平台且用户已有绑定沙箱）。
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
SHARED_DIR = "/home/user/shared"


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
        detail = e.read()[:200].decode(errors="replace")
        raise RuntimeError(f"HTTP {e.code} {url}: {detail}") from e


def pod_run(deploy_args: list[str], script: str) -> str:
    proc = subprocess.run(
        [*deploy_args, "--", "/app/.venv/bin/python", "-"],
        input=script.encode(),
        capture_output=True,
        timeout=180,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"in-pod helper failed: {proc.stderr.decode()[:300]}")
    return proc.stdout.decode().strip()


def mint_script(user_id: str) -> str:
    return (
        "import asyncio\n"
        "async def main():\n"
        "    from src.infra.auth.jwt import create_access_token\n"
        f"    print(create_access_token({user_id!r}, expires_delta=None))\n"
        "asyncio.run(main())\n"
    )


def binding_script(user_id: str) -> str:
    return (
        "import asyncio\n"
        "async def main():\n"
        "    from src.kernel.config import settings\n"
        "    from src.infra.storage.mongodb import get_mongo_client\n"
        "    c = get_mongo_client()\n"
        "    d = await c[settings.MONGODB_DB]['user_sandbox_bindings'].find_one("
        f"{{'user_id': {user_id!r}}})\n"
        "    print(d.get('sandbox_id') if d else 'NONE')\n"
        "asyncio.run(main())\n"
    )


def pause_script(user_id: str) -> str:
    return (
        "import asyncio\n"
        "async def main():\n"
        "    from src.kernel.config import settings\n"
        "    from src.kernel.config.service import initialize_settings\n"
        "    await initialize_settings()\n"
        "    from src.infra.storage.mongodb import get_mongo_client\n"
        "    from src.infra.sandbox._adapters import E2BSandboxAdapter\n"
        "    c = get_mongo_client()\n"
        "    d = await c[settings.MONGODB_DB]['user_sandbox_bindings'].find_one("
        f"{{'user_id': {user_id!r}}})\n"
        "    sbx_id = (d or {}).get('sandbox_id')\n"
        "    if not sbx_id:\n"
        "        print('FAIL:no-binding'); return\n"
        "    a = E2BSandboxAdapter(api_key=settings.E2B_API_KEY, "
        "template=settings.E2B_TEMPLATE, timeout=settings.E2B_TIMEOUT)\n"
        "    s = a.get_sandbox(sbx_id)\n"
        "    if s is None:\n"
        "        print('FAIL:cannot-connect'); return\n"
        "    a.pause_sandbox(s)\n"
        "    st = a.get_sandbox_info(s).get('state')\n"
        "    print('OK:' + str(st))\n"
        "asyncio.run(main())\n"
    )


def chat_once(base: str, token: str, agent: str, session_id: str, message: str) -> tuple[str, str]:
    resp = http_json(
        f"{base}/api/chat/stream?agent_id={agent}",
        method="POST",
        token=token,
        body={"message": message, "session_id": session_id, "max_steps": 40},
    )
    run_id = resp["run_id"]
    deadline = time.time() + RUN_TIMEOUT_S
    while time.time() < deadline:
        time.sleep(POLL_INTERVAL_S)
        payload = http_json(f"{base}/api/sessions/{session_id}/runs", token=token)
        runs = payload if isinstance(payload, list) else payload.get("runs") or []
        match = next((r for r in runs if r.get("run_id") == run_id), None)
        if match and match.get("status") in {"completed", "error", "failed", "cancelled"}:
            return run_id, str(match.get("status"))
    return run_id, "timeout"


def run_text_and_problems(
    base: str, token: str, session_id: str, run_id: str
) -> tuple[str, list[str]]:
    payload = http_json(f"{base}/api/sessions/{session_id}/events", token=token)
    events = payload if isinstance(payload, list) else payload.get("events") or []
    mine = [e for e in events if e.get("run_id") == run_id]
    problems: list[str] = []
    for e in mine:
        etype = e.get("event_type", "")
        data = json.dumps(e.get("data", {}), ensure_ascii=False)
        if etype == "error":
            problems.append(f"error事件: {data[:150]}")
        if etype == "tool:result" and ("Command failed" in data or "timed out" in data.lower()):
            problems.append(f"工具失败: {data[:150]}")
    text = "".join(
        e.get("data", {}).get("content", "") for e in mine if e.get("event_type") == "message:chunk"
    )
    return text, problems


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="https://lambchat.com")
    parser.add_argument("--namespace", default="lambchat")
    parser.add_argument("--deployment", default="lambchat-a")
    parser.add_argument("--kubectl-cmd", default="kubectl")
    parser.add_argument("--user-id", required=True, help="已有绑定沙箱的用户（如 disttest）")
    parser.add_argument("--agent", default="team")
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
    user_id = args.user_id
    results: list[tuple[str, bool]] = []

    def check(name: str, cond: bool, detail: str = "") -> None:
        results.append((name, bool(cond)))
        suffix = f"  {detail}" if detail and not cond else ""
        print(("✅ PASS  " if cond else "❌ FAIL  ") + name + suffix)

    ok = False
    detail = ""
    try:
        token = pod_run(deploy_args, mint_script(user_id))
        marker_a = f"CROSS-A-{secrets.token_hex(3)}"
        marker_b = f"CROSS-B-{secrets.token_hex(3)}"
        shared_marker = f"SHARED-{secrets.token_hex(3)}"
        sid_a = f"cross-a-{secrets.token_hex(3)}"
        sid_b = f"cross-b-{secrets.token_hex(3)}"

        sbx_before = pod_run(deploy_args, binding_script(user_id))
        print(f"[info] binding sandbox before: {sbx_before}")
        if sbx_before == "NONE":
            raise AssertionError("用户无绑定沙箱（先跑一次 verify_sandbox_pause_heal.py）")

        # 会话 A：写私有文件 + 共享文件
        rid, status = chat_once(
            base,
            token,
            args.agent,
            sid_a,
            f"依次执行这三条命令并把关键输出原样贴给我："
            f"1) echo {marker_a} > sess-a.txt; "
            f"2) mkdir -p {SHARED_DIR} && echo {shared_marker} > {SHARED_DIR}/shared-note.txt; "
            f"3) cat sess-a.txt {SHARED_DIR}/shared-note.txt",
        )
        print(f"[A1] {status}")
        text, problems = run_text_and_problems(base, token, sid_a, rid)
        check(
            "A1 会话A写入+回显",
            status == "completed" and not problems and marker_a in text and shared_marker in text,
            f"{problems} {text[:150]}",
        )

        pout = pod_run(deploy_args, pause_script(user_id))
        print(f"[pause] {pout}")
        check("A→暂停 state=paused", pout == "OK:paused", pout)

        # 会话 B（同用户新会话）：隔离 + 共享可见
        rid, status = chat_once(
            base,
            token,
            args.agent,
            sid_b,
            f"依次执行这四条命令，每条输出原样贴给我（报错也原样贴）："
            f"1) ls; 2) cat sess-a.txt; 3) echo {marker_b} > sess-b.txt; "
            f"4) cat {SHARED_DIR}/shared-note.txt && cat sess-b.txt",
        )
        print(f"[B1] {status}")
        text, problems = run_text_and_problems(base, token, sid_b, rid)
        # B2 的隔离探测（cat sess-a.txt）按设计必然报 No such file——
        # 那是隔离的证据而非异常，不计入 B1；其余失败仍判 B1 失败
        unexpected = [p for p in problems if not ("sess-a.txt" in p and "No such file" in p)]
        check(
            "B1 会话B零报错完成（隔离探测除外）",
            status == "completed" and not unexpected,
            str(unexpected),
        )
        check("B2 会话隔离（B 看不到 A 的 sess-a.txt）", "No such file" in text, text[:200])
        check("B3 跨会话共享目录可读", shared_marker in text, text[:200])
        check("B4 会话B可写入", marker_b in text, text[:200])

        # 再暂停，回 A 验证完整性
        pout = pod_run(deploy_args, pause_script(user_id))
        print(f"[pause2] {pout}")
        rid, status = chat_once(
            base, token, args.agent, sid_a, "执行 cat sess-a.txt，把输出原样贴给我。"
        )
        print(f"[A2] {status}")
        text, problems = run_text_and_problems(base, token, sid_a, rid)
        check(
            "A2 回会话A文件完整（两次暂停后）",
            status == "completed" and not problems and marker_a in text,
            f"{problems} {text[:150]}",
        )

        sbx_after = pod_run(deploy_args, binding_script(user_id))
        print(f"[info] binding sandbox after: {sbx_after}")
        check(
            "绑定沙箱全程未重建",
            sbx_before == sbx_after and sbx_before != "NONE",
            f"{sbx_before} -> {sbx_after}",
        )

        ok = all(cond for _, cond in results)
        detail = "cross-session isolation/shared/intact, sandbox reused"
    except Exception as exc:  # noqa: BLE001
        detail = str(exc)[:300]
        print(f"❌ FAIL  {detail}")

    passed = sum(1 for _, cond in results if cond)
    print(f"\n===== 跨对话检验: {passed}/{len(results)} PASS =====")
    print("RESULT:" + json.dumps({"ok": ok, "detail": detail}, ensure_ascii=False))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
