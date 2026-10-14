#!/usr/bin/env python3
"""沙箱二进制文件完整性检验（2026-10-14 生产事故的部署后门禁）。

事故：CubeSandbox 的 files.read 恒返回 lossy 解码文本，Word/PDF 等二进制
经 download_files 交付时字节被 U+FFFD 替换破坏；E2B async 车道因管理器
平台快照失效恒降级线程车道（issue #877）。本脚本在目标环境的真实沙箱
后端上做字节级 round-trip 校验，四个云平台（e2b/cubesandbox/daytona）
全适用，local 平台输出 SKIP。

覆盖：
  T1 上传→下载字节精确（3MB 高熵二进制，含非法 UTF-8 序列）
  T2 沙箱内生成（模拟 agent 写文件）→下载 sha256 一致
  T3 read() 二进制走 base64 FileData，解码后 sha256 一致
  T4 大文件分块通道（48MB 逼近下载上限，Cube 侧 3×16MiB 分块）
  T5 文本读写回归（不得因二进制检测误伤）
  T6 async 车道字节精确 + async 客户端可用性（#877 观测点）

用法（在本机或运维机上跑，通过 kubectl 操作目标集群）：
  # 生产（复用 disttest 用户）：
  python3 scripts/verify_sandbox_binary_integrity.py \
      --base-url https://lambchat.com --namespace lambchat --deployment lambchat-a \
      --user-id 6999be7275bdd6b1d868075b
  # staging（一次性注册测试用户，结束自动回收）：
  python3 scripts/verify_sandbox_binary_integrity.py \
      --base-url https://test.lambchat.com --namespace lambchat-staging \
      --deployment lambchat-staging --register

输出：人读 ✅/❌ 行 + 末行 RESULT:{"ok":true/false,...}（供 run-all.sh 采集）。
退出码：0 = PASS/SKIP，1 = FAIL。仅用标准库；测试文件随手清理。
"""

from __future__ import annotations

import argparse
import json
import secrets
import subprocess
import sys
import urllib.error
import urllib.request
from typing import Any

RUN_TIMEOUT_S = 300


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


def kubectl_exec(deploy_args: list[str], pod_script: str, timeout: int = 280) -> str:
    """把 python 脚本喂进目标 deployment 的 venv python，返回 stdout。"""
    cmd = [*deploy_args, "--", "/app/.venv/bin/python", "-"]
    proc = subprocess.run(cmd, input=pod_script.encode(), capture_output=True, timeout=timeout)
    out = proc.stdout.decode(errors="replace").strip()
    if proc.returncode != 0:
        raise RuntimeError(
            f"in-pod helper failed (rc={proc.returncode}): {proc.stderr.decode()[:400]}"
        )
    return out


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
    if binding and binding.get("sandboxes"):
        from src.kernel.config.service import initialize_settings
        await initialize_settings()
        for platform, scoped in (binding.get("sandboxes") or {}).items():
            sid = (scoped or {}).get("sandbox_id")
            if not sid:
                continue
            try:
                if platform == "e2b":
                    from src.infra.sandbox._adapters import E2BSandboxAdapter as Adapter
                    adapter = Adapter(api_key=settings.E2B_API_KEY,
                                      template=settings.E2B_TEMPLATE,
                                      timeout=settings.E2B_TIMEOUT)
                elif platform == "cubesandbox":
                    from src.infra.sandbox._adapters import CubeSandboxAdapter as Adapter
                    adapter = Adapter(api_url=settings.CUBE_API_URL,
                                      template=settings.CUBE_TEMPLATE,
                                      proxy_node_ip=settings.CUBE_PROXY_NODE_IP,
                                      proxy_port_http=settings.CUBE_PROXY_PORT_HTTP,
                                      sandbox_domain=settings.CUBE_SANDBOX_DOMAIN,
                                      timeout=settings.CUBE_TIMEOUT,
                                      request_timeout=settings.CUBE_REQUEST_TIMEOUT)
                else:
                    continue
                sbx = adapter.get_sandbox(sid)
                if sbx is not None:
                    adapter.kill_sandbox(sbx)
            except Exception as exc:
                print("sandbox-kill-skipped:", platform, exc)
    if uid:
        for coll in ("user_sandbox_bindings", "sessions", "traces"):
            await db[coll].delete_many({"user_id": uid})
        await db["users"].delete_one({"_id": user["_id"]})
    print("cleaned")

asyncio.run(main())
"""

# in-pod 主检验脚本：占位符 USER_ID / SESSION_TAG 由 .replace 注入。
VERIFY_SCRIPT = r"""
import asyncio, hashlib, json, os, sys, time

RESULTS = []

def record(name, ok, detail=""):
    RESULTS.append({"name": name, "ok": bool(ok), "detail": str(detail)[:200]})
    print(("PASS " if ok else "FAIL ") + name + ((" :: " + str(detail)[:200]) if detail and not ok else ""))

async def main():
    from src.kernel.config import settings
    from src.kernel.config.service import initialize_settings
    await initialize_settings()
    platform = settings.SANDBOX_PLATFORM.lower()
    if platform not in {"e2b", "cubesandbox", "daytona"}:
        print("SKIP:not-supported:" + platform)
        return
    from src.infra.sandbox.session_manager import SessionSandboxManager
    manager = SessionSandboxManager()
    backend, work_dir = await manager.get_or_create(SESSION_TAG, USER_ID)
    print(f"[env] platform={platform} work_dir={work_dir}")
    sys.stdout.flush()

    import base64 as b64mod

    def sha(data: bytes) -> str:
        return hashlib.sha256(data).hexdigest()

    small = os.urandom(3 * 1024 * 1024)
    big = os.urandom(48 * 1024 * 1024)  # 逼近 50MB 下载上限；Cube 侧 3×16MiB 分块

    # T1 上传→下载字节精确
    t0 = time.monotonic()
    r = backend.upload_files([("bin-t1.bin", small)])
    if r and r[0].error:
        record("T1_upload_download_roundtrip", False, r[0].error)
    else:
        d = backend.download_files(["bin-t1.bin"])
        elapsed = time.monotonic() - t0
        print(f"[T1] 3MB upload+download {elapsed:.1f}s")
        record("T1_upload_download_roundtrip",
               bool(d and d[0].error is None and d[0].content is not None
                    and sha(d[0].content) == sha(small)),
               d[0].error if d else "no response")

    # T2 沙箱内生成（模拟 agent 写文件）→下载
    res = backend.execute(
        "python3 -c \"import os,hashlib,sys;"
        "d=os.urandom(3*1024*1024);"
        "open(sys.argv[1],'wb').write(d);"
        "print(hashlib.sha256(d).hexdigest())\" bin-t2.bin"
    )
    if res.exit_code != 0:
        record("T2_agent_created_binary", False, (res.output or "")[:120])
    else:
        expected = (res.output or "").strip().split()[-1]
        d = backend.download_files(["bin-t2.bin"])
        record("T2_agent_created_binary",
               bool(d and d[0].error is None and d[0].content
                    and sha(d[0].content) == expected))

    # T3 read() 二进制 → base64 FileData（≤2MB 读取上限）
    tiny = os.urandom(1024 * 1024)
    backend.upload_files([("bin-t3.bin", tiny)])
    rr = backend.read("bin-t3.bin")
    ok = rr.error is None and rr.file_data and rr.file_data.get("encoding") == "base64" \
        and sha(b64mod.b64decode(rr.file_data["content"])) == sha(tiny)
    record("T3_read_binary_base64", ok,
           rr.error or (rr.file_data or {}).get("encoding"))

    # T4 大文件分块通道（48MB，逼近 50MB 下载上限）
    t0 = time.monotonic()
    r = backend.upload_files([("bin-t4.bin", big)])
    if r and r[0].error:
        record("T4_large_file_chunks", False, r[0].error)
    else:
        d = backend.download_files(["bin-t4.bin"])
        elapsed = time.monotonic() - t0
        print(f"[T4] 48MB upload+download {elapsed:.1f}s ({48 / elapsed:.1f} MB/s)" if elapsed > 0 else "[T4] done")
        record("T4_large_file_chunks",
               bool(d and d[0].error is None and d[0].content
                    and sha(d[0].content) == sha(big)))

    # T5 文本读写回归
    backend.write("text-t5.txt", "纯文本第一行\nsecond line\n")
    rr = backend.read("text-t5.txt")
    record("T5_text_read_regression",
           rr.error is None and "纯文本第一行" in (rr.file_data or {}).get("content", ""))

    # T6 async 车道（#877 观测点）：客户端可用性 + 字节精确
    async_client_up = False
    try:
        sbx = await backend._async_client_or_none()
        async_client_up = sbx is not None
    except Exception as exc:  # noqa: BLE001
        print("[T6] async client probe error:", exc)
    ad = await backend.adownload_files(["bin-t1.bin"])
    record("T6_async_download_bytes",
           bool(ad and ad[0].error is None and ad[0].content
                and sha(ad[0].content) == sha(small)),
           ad[0].error if ad else "no response")
    print(f"[T6] async_client_up={async_client_up}")

    # 清理测试文件
    backend.execute("rm -f bin-t1.bin bin-t2.bin bin-t3.bin bin-t4.bin text-t5.txt")

    print("RESULT_JSON:" + json.dumps(
        {"ok": all(x["ok"] for x in RESULTS), "platform": platform,
         "async_client_up": async_client_up, "tests": RESULTS}, ensure_ascii=False))

asyncio.run(main())
"""


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
        if args.user_id:
            user_id = args.user_id
        else:
            register_user = f"binint-{secrets.token_hex(4)}"
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
        print(f"[user] user_id={user_id} mode={'register' if register_user else 'reuse'}")

        session_tag = f"bin-integrity-{secrets.token_hex(3)}"
        script = VERIFY_SCRIPT.replace("USER_ID", repr(user_id)).replace(
            "SESSION_TAG", repr(session_tag)
        )
        out = kubectl_exec(deploy_args, script, timeout=RUN_TIMEOUT_S)
        print(out)
        result_line = next((ln for ln in out.splitlines() if ln.startswith("RESULT_JSON:")), "")
        if out.startswith("SKIP:"):
            print(f"✅ SKIP  平台不适用（{out}）")
            print('RESULT:{"ok": true, "skip": true, "reason": "' + out + '"}')
            return 0
        if not result_line:
            raise AssertionError("in-pod 脚本未输出 RESULT_JSON")
        payload = json.loads(result_line[len("RESULT_JSON:") :])
        ok = bool(payload.get("ok"))
        detail = (
            f"platform={payload.get('platform')} "
            f"async_client_up={payload.get('async_client_up')} "
            f"failed={[t['name'] for t in payload.get('tests', []) if not t['ok']]}"
        )
        if ok:
            print("✅ PASS  二进制完整性全项通过")
        else:
            print(f"❌ FAIL  {detail}")
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
