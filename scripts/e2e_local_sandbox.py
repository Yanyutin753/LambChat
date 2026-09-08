"""本地沙箱 daemon ↔ 服务端链路 E2E（平台开发硬性验证，见 AGENTS.md 验证指南）。

用法：
  uv run python scripts/e2e_local_sandbox.py             # 全量功能链路
  uv run python scripts/e2e_local_sandbox.py --stress    # 追加压测段（并发扫描 + 持续负载）

前置：本机 MongoDB / Redis 可达（凭据读仓库 .env）；后端未起时自动拉起并在退出时回收。
覆盖：SSE 握手与注册表 / machines 与 status 在线 / exec 往返 / 机器绑定防冒答 /
双向流式传输（2MB 二进制 sha256 校验）/ 结构化 fs op / 分块 base64 兜底 / 优雅下线。

输出：逐项 PASS/FAIL 与汇总；任一 FAIL 退出码非零。
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import hashlib
import json
import os
import secrets
import shutil
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))  # src.* 可导入

SERVER = os.environ.get("E2E_SANDBOX_SERVER", "http://127.0.0.1:8000")
WORKSPACE_ROOT = Path("/tmp/lambchat-sbx-e2e")

_results: list[tuple[str, bool, str]] = []
_PAT_HOLDER: dict = {"pat": ""}


def check(name: str, ok: bool, note: str = "") -> None:
    _results.append((name, ok, note))
    print(f"{'✅ PASS' if ok else '❌ FAIL'}  {name}" + (f"  — {note}" if note else ""), flush=True)


def http_json(
    method: str,
    path: str,
    body: dict | None = None,
    token: str | None = None,
    timeout: float = 10.0,
    query: str = "",
):
    url = f"{SERVER}{path}{query}"
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.status, json.loads(resp.read() or b"{}")


# ---------- 环境装配 ----------


def _env_map() -> dict[str, str]:
    out: dict[str, str] = {}
    env_file = REPO / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                out[k.strip()] = v.split(" #")[0].strip()
    return out


def ensure_backend() -> subprocess.Popen | None:
    """后端在跑返回 None；否则拉起一个并在退出时由调用方回收。"""
    try:
        urllib.request.urlopen(f"{SERVER}/api/version", timeout=2).read()
        print(f"[env] 后端已在运行：{SERVER}")
        return None
    except Exception:
        proc = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "uvicorn",
                "src.api.main:app",
                "--host",
                "127.0.0.1",
                "--port",
                "8000",
            ],
            cwd=REPO,
            stdout=open("/tmp/e2e-backend.log", "w"),
            stderr=subprocess.STDOUT,
        )
        for _ in range(30):
            time.sleep(1)
            try:
                urllib.request.urlopen(f"{SERVER}/api/version", timeout=2).read()
                print(f"[env] 已自动拉起后端 pid={proc.pid}（日志 /tmp/e2e-backend.log）")
                return proc
            except Exception:
                continue
        raise RuntimeError("后端 30s 未就绪，查 /tmp/e2e-backend.log")


def mongo_activate_user(username: str) -> None:
    env = _env_map()
    url = env.get("MONGODB_URL", "mongodb://localhost:27017")
    user, pwd = env.get("MONGODB_USERNAME", ""), env.get("MONGODB_PASSWORD", "")
    auth_src = env.get("MONGODB_AUTH_SOURCE", "admin")
    db_name = env.get("MONGODB_DB", "agent_state")
    if user and pwd:
        head = url.rstrip("/")
        sep = "?" if "?" in head else "/"
        url = f"{head}{sep}authSource={auth_src}" if "@" not in url else url
        # 凭据走 MongoClient 参数而非拼 URL（密码特殊字符安全）
        import pymongo

        client = pymongo.MongoClient(
            url, username=user, password=pwd, authSource=auth_src, serverSelectionTimeoutMS=3000
        )
    else:
        import pymongo

        client = pymongo.MongoClient(url, serverSelectionTimeoutMS=3000)
    r = client[db_name].users.update_one(
        {"username": username}, {"$set": {"is_active": True, "email_verified": True}}
    )
    if r.matched_count != 1:
        raise RuntimeError(f"测试用户未注册成功：{username}")


def cleanup_user(username: str) -> None:
    try:
        env = _env_map()
        import pymongo

        url = env.get("MONGODB_URL", "mongodb://localhost:27017")
        user, pwd = env.get("MONGODB_USERNAME", ""), env.get("MONGODB_PASSWORD", "")
        auth_src = env.get("MONGODB_AUTH_SOURCE", "admin")
        db_name = env.get("MONGODB_DB", "agent_state")
        client = pymongo.MongoClient(
            url,
            username=user or None,
            password=pwd or None,
            authSource=auth_src,
            serverSelectionTimeoutMS=3000,
        )
        db = client[db_name]
        u = db.users.find_one({"username": username}, {"_id": 1})
        if u:
            db.pats.delete_many({"user_id": str(u["_id"])})
            db.users.delete_one({"_id": u["_id"]})
    except Exception as exc:  # noqa: BLE001 - 清理尽力而为
        print(f"[cleanup] 用户清理跳过：{exc}")


def mint_pat(username: str, password: str) -> tuple[str, str]:
    http_json(
        "POST",
        "/api/auth/register",
        {"username": username, "password": password, "email": f"{username}@example.com"},
    )
    mongo_activate_user(username)
    _, login = http_json("POST", "/api/auth/login", {"username": username, "password": password})
    _, pat = http_json(
        "POST",
        "/api/auth/pat",
        {"name": "e2e-local-sandbox", "scopes": ["sandbox:execute"]},
        token=login["access_token"],
    )
    return pat["token"], login["access_token"]


def spawn_daemon(pat: str, machine_id: str) -> subprocess.Popen:
    proc = subprocess.Popen(
        [sys.executable, str(Path(__file__).resolve()), "--daemon-child", pat, machine_id],
        cwd=REPO,
        stdout=open("/tmp/e2e-daemon.log", "w"),
        stderr=subprocess.STDOUT,
    )
    for _ in range(20):
        time.sleep(0.5)
        try:
            _, body = http_json("GET", "/api/sandbox/machines", token=pat)
            if any(m["machine_id"] == machine_id and m["online"] for m in body["machines"]):
                return proc
        except Exception:
            continue
    raise RuntimeError(f"daemon 10s 未上线，查 /tmp/e2e-daemon.log（pid={proc.pid}）")


# ---------- 测试电池 ----------


async def battery(user_id: str, pat: str, machine_id: str) -> None:
    from src.infra.sandbox.relay.dispatch import (
        dispatch_local_call,
        dispatch_local_stream,
        dispatch_local_stream_upload,
    )

    # 1. 在线状态
    _, machines = http_json("GET", "/api/sandbox/machines", token=pat)
    m = next((x for x in machines["machines"] if x["machine_id"] == machine_id), None)
    check(
        "machines 在线 + last_seen",
        m is not None and m["online"] and m.get("last_seen") is not None,
        f"{m['machine_id']} v{m.get('version')}",
    )
    _, status = http_json("GET", "/api/sandbox/status", token=pat)
    check("status 在线", status.get("online") is True)

    # 2. exec 往返（含中文/命令替换/多行）
    t0 = time.monotonic()
    r = await dispatch_local_call(
        user_id,
        "exec",
        {"command": "echo e2e-$(hostname) && echo 中文行", "cwd": "/workspace/e2e"},
        machine_id=machine_id,
    )
    check(
        "exec 往返",
        r.get("status") == "ok"
        and "e2e-" in r.get("stdout", "")
        and "中文行" in r.get("stdout", ""),
        f"exit={r.get('exit_code')} {(time.monotonic() - t0) * 1000:.0f}ms",
    )

    # 3. 防冒答：在飞调用以他机身份回传 → 409 sandbox_result_mismatch
    import redis.asyncio as aioredis

    env = _env_map()
    slow = asyncio.create_task(
        dispatch_local_call(
            user_id,
            "exec",
            {"command": "sleep 3 && echo real", "cwd": "/workspace/e2e"},
            machine_id=machine_id,
        )
    )
    red = aioredis.from_url(env.get("REDIS_URL", "redis://127.0.0.1:6379/0"))
    call_id = None
    for _ in range(60):
        keys = await red.keys("sandbox:callassign:*")
        if keys:
            call_id = keys[0].split(b":")[-1].decode()
            break
        await asyncio.sleep(0.05)
    await red.aclose()
    spoof_code = None
    try:
        http_json(
            "POST",
            f"/api/sandbox/results/{call_id}",
            {"stage": "done", "status": "ok", "stdout": "FAKED"},
            token=pat,
            query="?machine_id=evil-machine",
        )
    except urllib.error.HTTPError as exc:
        spoof_code = json.loads(exc.read()).get("detail", {}).get("code")
    real = await slow
    check(
        "防冒答 409 + 真实结果不受污染",
        spoof_code == "sandbox_result_mismatch" and real.get("stdout", "").strip() == "real",
        f"code={spoof_code}",
    )

    # 4. 双向流式：大文件二进制（图片/归档形态）上传 + 下载 sha256 校验
    #    三档尺寸看吞吐线性度（10/50/100MB），max_bytes 覆盖最大档。
    for size_mb in (10, 50, 100):
        payload = b"\x89PNG\r\n\x1a\n" + secrets.token_bytes(size_mb * 1024 * 1024 - 8)
        want = hashlib.sha256(payload).hexdigest()
        t0 = time.monotonic()
        await dispatch_local_stream_upload(
            user_id,
            {
                "cwd": "/workspace/e2e",
                "path": f"imgs/e2e-{size_mb}m.bin",
                "max_bytes": 200 * 1024 * 1024,
            },
            payload,
            machine_id=machine_id,
        )
        up_s = time.monotonic() - t0
        chunks = []
        t1 = time.monotonic()
        async for chunk in dispatch_local_stream(
            user_id,
            "fs_download_stream",
            {
                "cwd": "/workspace/e2e",
                "path": f"imgs/e2e-{size_mb}m.bin",
                "max_bytes": 200 * 1024 * 1024,
            },
            timeout=300.0,
            machine_id=machine_id,
        ):
            chunks.append(chunk)
        down_s = time.monotonic() - t1
        got = hashlib.sha256(b"".join(chunks)).hexdigest()
        mbps = lambda secs, n: n / 1024 / 1024 / secs if secs > 0 else 0  # noqa: E731
        check(
            f"流式上传+下载 {size_mb}MB sha256 一致",
            got == want,
            f"上 {mbps(up_s, len(payload)):.0f}MB/s · 下 {mbps(down_s, len(payload)):.0f}MB/s",
        )

    # 5. 结构化 fs op：fs_write / fs_read
    txt = "LambChat E2E 文本校验 " * 20
    w = await dispatch_local_call(
        user_id,
        "fs_write",
        {
            "cwd": "/workspace/e2e",
            "path": "notes/e2e.txt",
            "content_b64": base64.b64encode(txt.encode()).decode(),
        },
        machine_id=machine_id,
    )
    rd = await dispatch_local_call(
        user_id,
        "fs_read",
        {"cwd": "/workspace/e2e", "path": "notes/e2e.txt"},
        machine_id=machine_id,
    )
    check(
        "fs_write + fs_read 内容一致",
        "error" not in (w.get("result") or {}) and (rd.get("result") or {}).get("content") == txt,
    )

    # 6. 分块 base64 兜底路径（fs_upload offset/truncate + fs_download 分片到 eof）
    blob = secrets.token_bytes(5 * 1024 * 1024)
    off, first, up_err = 0, True, None
    while off < len(blob) or first:
        d = await dispatch_local_call(
            user_id,
            "fs_upload",
            {
                "cwd": "/workspace/e2e",
                "path": "blobs/e2e.bin",
                "content_b64": base64.b64encode(blob[off : off + 128 * 1024]).decode(),
                "offset": off,
                "truncate": first,
            },
            machine_id=machine_id,
        )
        if "error" in (d.get("result") or {}):
            up_err = d["result"]["error"]
            break
        off += 128 * 1024
        first = False
    parts, off, dl_err = [], 0, None
    while up_err is None:
        d = await dispatch_local_call(
            user_id,
            "fs_download",
            {"cwd": "/workspace/e2e", "path": "blobs/e2e.bin", "offset": off, "length": 128 * 1024},
            machine_id=machine_id,
        )
        res = d.get("result") or {}
        if "error" in res:
            dl_err = res["error"]
            break
        parts.append(base64.b64decode(res.get("content_b64") or ""))
        off += len(parts[-1])
        if res.get("eof"):
            break
    check(
        "分块 base64 上传+下载一致",
        up_err is None and dl_err is None and b"".join(parts) == blob,
        f"{len(blob) // (1024 * 1024)}MiB",
    )


async def edge_cases(user_id: str, machine_id: str) -> None:
    """边界专项：安全拒绝、超时语义、空文件、会话隔离、超限、伪超帧。"""
    import httpx

    from src.infra.sandbox.relay.dispatch import dispatch_local_call
    from src.kernel.errors import AppError

    # E1. 路径逃逸：fs_read path 含 ../ 必拒
    r = await dispatch_local_call(
        user_id,
        "fs_read",
        {"cwd": "/workspace/e2e", "path": "../../../etc/passwd"},
        machine_id=machine_id,
    )
    err1 = (r.get("result") or {}).get("error", "")
    check("路径逃逸拒绝", bool(err1), str(err1)[:60])

    # E2. 非 workspace cwd 的 exec 必拒（工作区锁）
    r = await dispatch_local_call(
        user_id, "exec", {"command": "cat /etc/hostname", "cwd": "/etc"}, machine_id=machine_id
    )
    check(
        "非工作区 cwd 拒绝",
        r.get("status") == "error" and "workspace" in str(r.get("error", "")),
        str(r.get("error", ""))[:60],
    )

    # E3. 超时语义：sleep 超过 exec timeout → SANDBOX_TIMEOUT（不挂死）

    t0 = time.monotonic()
    code3 = None
    try:
        await dispatch_local_call(
            user_id,
            "exec",
            {"command": "sleep 30", "cwd": "/workspace/e2e"},
            machine_id=machine_id,
            timeout=3.0,
        )
    except AppError as exc:
        code3 = getattr(exc.error_code, "code", str(exc.error_code))
    check(
        "exec 超时显式报错",
        code3 == "sandbox_timeout",
        f"code={code3} 用时{time.monotonic() - t0:.1f}s",
    )

    # E4. 0 字节文件流式往返
    from src.infra.sandbox.relay.dispatch import dispatch_local_stream, dispatch_local_stream_upload

    await dispatch_local_stream_upload(
        user_id,
        {"cwd": "/workspace/e2e", "path": "edge/empty.bin", "max_bytes": 1024},
        b"",
        machine_id=machine_id,
    )
    parts4 = []
    async for chunk in dispatch_local_stream(
        user_id,
        "fs_download_stream",
        {"cwd": "/workspace/e2e", "path": "edge/empty.bin", "max_bytes": 1024},
        timeout=30.0,
        machine_id=machine_id,
    ):
        parts4.append(chunk)
    check("0 字节文件往返", b"".join(parts4) == b"")

    # E5. 中文/空格文件名 fs_write + fs_read
    name5 = "笔记 2026 最终版.txt"
    txt5 = "边界文件名内容"
    await dispatch_local_call(
        user_id,
        "fs_write",
        {
            "cwd": "/workspace/e2e",
            "path": f"edge/{name5}",
            "content_b64": base64.b64encode(txt5.encode()).decode(),
        },
        machine_id=machine_id,
    )
    r = await dispatch_local_call(
        user_id,
        "fs_read",
        {"cwd": "/workspace/e2e", "path": f"edge/{name5}"},
        machine_id=machine_id,
    )
    check("中文/空格文件名", (r.get("result") or {}).get("content") == txt5)

    # E6. 会话隔离：e2e 会话写文件，另一会话经 ../ 读不到
    await dispatch_local_call(
        user_id,
        "fs_write",
        {
            "cwd": "/workspace/e2e",
            "path": "iso.txt",
            "content_b64": base64.b64encode(b"secret").decode(),
        },
        machine_id=machine_id,
    )
    r = await dispatch_local_call(
        user_id,
        "fs_read",
        {"cwd": "/workspace/other-session", "path": "../e2e/iso.txt"},
        machine_id=machine_id,
    )
    res6 = r.get("result") or {}
    check(
        "会话隔离（跨会话访问被拒）",
        bool(res6.get("error")) and res6.get("content") is None,
        str(res6.get("error"))[:60],
    )

    # E7. 超限拒绝：下载 max_bytes < 文件大小 → file_too_large（流式）
    payload7 = secrets.token_bytes(64 * 1024)
    await dispatch_local_stream_upload(
        user_id,
        {"cwd": "/workspace/e2e", "path": "edge/64k.bin", "max_bytes": 1024 * 1024},
        payload7,
        machine_id=machine_id,
    )
    err7 = None
    try:
        async for _ in dispatch_local_stream(
            user_id,
            "fs_download_stream",
            {"cwd": "/workspace/e2e", "path": "edge/64k.bin", "max_bytes": 1024},
            timeout=30.0,
            machine_id=machine_id,
        ):
            pass
    except AppError as exc:
        err7 = str(getattr(exc, "args_data", {}).get("detail") or exc.message)
    check("下载超限显式拒绝", err7 is not None and "file_too_large" in err7, str(err7)[:60])

    # E8. 伪造超帧（>8MiB 单帧）→ 端点 413（帧上限防线）
    import sys as _sys

    _sys.path.insert(0, str(REPO / "client"))
    from lambchat_sandbox.frames import FRAME_DATA, FRAME_EOF, encode_frame

    async with httpx.AsyncClient() as hc:
        resp8 = await hc.post(
            f"{SERVER}/api/sandbox/results/stream/edge-oversize",
            content=encode_frame(FRAME_DATA, b"x" * (9 * 1024 * 1024)) + encode_frame(FRAME_EOF),
            headers={
                "Authorization": f"Bearer {_PAT_HOLDER['pat']}",
                "Content-Type": "application/octet-stream",
            },
            timeout=30,
        )
    check("伪超帧 413", resp8.status_code == 413, f"HTTP {resp8.status_code}")


async def crash_recovery(user_id: str, pat: str, machine_id: str, holder: dict) -> None:
    """daemon SIGKILL（无 post_offline）→ 在飞调用显式失败不挂死 → 同身份重启恢复。"""
    from src.infra.sandbox.relay.dispatch import dispatch_local_call
    from src.kernel.errors import AppError

    proc = holder["proc"]
    task = asyncio.create_task(
        dispatch_local_call(
            user_id,
            "exec",
            {"command": "sleep 8 && echo done", "cwd": "/workspace/e2e"},
            machine_id=machine_id,
            timeout=6.0,
        )
    )
    await asyncio.sleep(1.0)  # 等请求入队进入在飞窗口
    proc.kill()  # SIGKILL：无优雅下线，机器键靠 35s TTL 过期
    proc.wait(timeout=5)
    code = None
    t0 = time.monotonic()
    try:
        await task
        code = "unexpectedly-succeeded"
    except AppError as exc:
        code = getattr(exc.error_code, "code", str(exc.error_code))
    check(
        "daemon SIGKILL 在飞调用显式失败",
        code == "sandbox_timeout",
        f"code={code} 用时{time.monotonic() - t0:.1f}s",
    )

    holder["proc"] = spawn_daemon(pat, machine_id)  # 同 machine_id 重启（真实身份复用）
    r = await dispatch_local_call(
        user_id,
        "exec",
        {"command": "echo recovered", "cwd": "/workspace/e2e"},
        machine_id=machine_id,
    )
    check(
        "daemon 重启后恢复服务",
        r.get("stdout", "").strip() == "recovered",
        f"exit={r.get('exit_code')}",
    )


async def comprehensive(user_id: str, pat: str, machine_id: str, holder: dict) -> None:
    """全方位段：fs op 全覆盖、多机并存定向分发、legacy daemon 混跑、上传中断哨兵。"""
    from src.infra.sandbox.relay.dispatch import dispatch_local_call
    from src.kernel.errors import AppError

    async def fs(op: str, payload: dict) -> dict:
        r = await dispatch_local_call(user_id, op, payload, machine_id=machine_id)
        return r.get("result") or {}

    # F1. fs_ls：目录列举
    r = await fs("fs_ls", {"cwd": "/workspace/e2e", "path": "."})
    names = " ".join(str(e.get("path", "")) for e in (r.get("entries") or []))
    check("fs_ls 目录列举", "edge" in names and "imgs" in names, names[:60])

    # F2. fs_glob：通配匹配（含中文文件名）
    r = await fs("fs_glob", {"cwd": "/workspace/e2e", "pattern": "edge/*.txt"})
    paths = " ".join(str(m.get("path", "")) for m in (r.get("matches") or []))
    check("fs_glob 通配匹配", "笔记" in paths, paths[:80])

    # F3. fs_grep：内容检索
    r = await fs("fs_grep", {"cwd": "/workspace/e2e", "pattern": "secret", "path": "."})
    check("fs_grep 内容检索", "error" not in r and bool(r.get("matches")), str(r)[:60])

    # F4. fs_edit：替换后读回
    import base64 as b64mod

    b64 = lambda t: b64mod.b64encode(t.encode()).decode()  # noqa: E731
    await fs(
        "fs_write",
        {"cwd": "/workspace/e2e", "path": "edge/edit.txt", "content_b64": b64("alpha beta gamma")},
    )
    r = await fs(
        "fs_edit",
        {
            "cwd": "/workspace/e2e",
            "path": "edge/edit.txt",
            "old_str_b64": b64("beta"),
            "new_str_b64": b64("BETA"),
        },
    )
    r2 = await fs("fs_read", {"cwd": "/workspace/e2e", "path": "edge/edit.txt"})
    check(
        "fs_edit 替换生效",
        "error" not in r and r2.get("content") == "alpha BETA gamma",
        str(r.get("error", r2.get("content")))[:40],
    )

    # F5. fs_delete：删除后读必 file_not_found
    await fs("fs_delete", {"cwd": "/workspace/e2e", "path": "edge/edit.txt"})
    r = await fs("fs_read", {"cwd": "/workspace/e2e", "path": "edge/edit.txt"})
    check("fs_delete 删除生效", r.get("error") == "file_not_found")

    # M1. 多机并存：第二台上线，双机在线 + 定向分发互不干扰
    machine_b = machine_id + "-b"
    daemon_b = spawn_daemon(pat, machine_b)
    try:
        _, machines = http_json("GET", "/api/sandbox/machines", token=pat)
        online_ids = {m["machine_id"] for m in machines["machines"] if m["online"]}
        rb = await dispatch_local_call(
            user_id,
            "exec",
            {"command": "echo from-b", "cwd": "/workspace/e2e"},
            machine_id=machine_b,
        )
        ra = await dispatch_local_call(
            user_id,
            "exec",
            {"command": "echo from-a", "cwd": "/workspace/e2e"},
            machine_id=machine_id,
        )
        check(
            "多机并存 + 定向分发",
            machine_id in online_ids
            and machine_b in online_ids
            and rb.get("stdout", "").strip() == "from-b"
            and ra.get("stdout", "").strip() == "from-a",
        )
    finally:
        daemon_b.terminate()
        daemon_b.wait(timeout=10)

    # M2. B 下线后 A 不受影响（5s 内 B 翻转离线）
    offline_b = False
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        _, machines = http_json("GET", "/api/sandbox/machines", token=pat)
        mb = next((m for m in machines["machines"] if m["machine_id"] == machine_b), None)
        if mb and not mb["online"]:
            offline_b = True
            break
        time.sleep(0.3)
    ra = await dispatch_local_call(
        user_id,
        "exec",
        {"command": "echo a-still-ok", "cwd": "/workspace/e2e"},
        machine_id=machine_id,
    )
    check("单机下线不连坐", offline_b and ra.get("stdout", "").strip() == "a-still-ok")

    # U1. 上传中断哨兵：大文件上传中 SIGKILL daemon → 调用方快速显式失败
    from src.infra.sandbox.relay.dispatch import dispatch_local_stream_upload

    big = secrets.token_bytes(400 * 1024 * 1024)
    t0 = time.monotonic()
    task = asyncio.create_task(
        dispatch_local_stream_upload(
            user_id,
            {
                "cwd": "/workspace/e2e",
                "path": "edge/interrupted.bin",
                "max_bytes": 200 * 1024 * 1024,
            },
            big,
            machine_id=machine_id,
        )
    )
    await asyncio.sleep(0.4)  # 帧已在途（回环 ~300MB/s，400MB 约 1.3s 传完）
    holder["proc"].kill()
    holder["proc"].wait(timeout=5)
    code_u, err_u = None, None
    try:
        await task
        code_u = "unexpectedly-succeeded"
    except AppError as exc:
        code_u = getattr(exc.error_code, "code", str(exc.error_code))
        err_u = str(getattr(exc, "args_data", {}).get("detail") or "")[:60]
    dt_u = time.monotonic() - t0
    check(
        "上传中断快速显式失败",
        code_u in ("sandbox_exec_failed", "sandbox_timeout"),
        f"code={code_u} {err_u} 用时{dt_u:.1f}s",
    )

    # 崩溃后同身份重启恢复（供后续 stress / 优雅下线继续）
    holder["proc"] = spawn_daemon(pat, machine_id)
    ra = await dispatch_local_call(
        user_id,
        "exec",
        {"command": "echo post-crash", "cwd": "/workspace/e2e"},
        machine_id=machine_id,
    )
    check("上传崩溃后重启恢复", ra.get("stdout", "").strip() == "post-crash")


async def agent_tools_battery(user_id: str, pat: str, machine_id: str) -> None:
    """agent 工具层（WorkspaceAliasBackend 生产链路）：别名路径映射、错误分类、
    动态超时（前端设置 PUT → 调用时读取 → 卡死命令到点击杀）。"""
    from src.infra.backend.local import WorkspaceAliasBackend

    # 生产同款：agent 一律传 /workspace/<sid>/x 别名路径，别名层剥离翻译
    backend = WorkspaceAliasBackend(user_id=user_id, session_id="agent-e2e", machine_id=machine_id)

    # A1. awrite/aread：别名路径往返（剥离 → cwd 映射 → 结果回填别名）
    await backend.awrite("/workspace/agent-e2e/agent/hi.txt", "hello agent")
    rd = await backend.aread("/workspace/agent-e2e/agent/hi.txt")
    fd1 = getattr(rd, "file_data", None)
    content1 = fd1.get("content") if isinstance(fd1, dict) else getattr(fd1, "content", None)
    check(
        "agent awrite/aread 别名路径",
        content1 == "hello agent",
        f"content={str(content1)[:30]!r} err={getattr(rd, 'error', None)}",
    )

    # A2. aedit：替换生效
    er = await backend.aedit("/workspace/agent-e2e/agent/hi.txt", "hello", "HELLO")
    rd = await backend.aread("/workspace/agent-e2e/agent/hi.txt")
    fd2 = getattr(rd, "file_data", None)
    content2 = fd2.get("content") if isinstance(fd2, dict) else getattr(fd2, "content", None)
    check(
        "agent aedit 替换",
        content2 == "HELLO agent",
        f"content={content2!r} err={getattr(er, 'error', None)}",
    )

    # A3. aglob：通配（matches 为 dict 列表）
    gr = await backend.aglob("agent/*.txt", "/workspace/agent-e2e")
    matches3 = getattr(gr, "matches", None) or []
    globs = [
        m.get("path", str(m)) if isinstance(m, dict) else getattr(m, "path", str(m))
        for m in matches3
    ]
    check("agent aglob 通配", any("hi.txt" in g for g in globs), ",".join(globs)[:60])

    # A4. agrep：检索
    pr = await backend.agrep("HELLO", "/workspace/agent-e2e/agent")
    check("agent agrep 检索", bool(getattr(pr, "matches", None)), str(pr)[:60])

    # A5. aexecute：正常命令 + 失败命令的错误可见性（agent 可自纠）
    ok5 = await backend.aexecute("echo agent-ok")
    bad5 = await backend.aexecute("cat /workspace/agent-e2e/definitely-missing.txt")
    check(
        "agent aexecute 正常+失败错误可见",
        "agent-ok" in (ok5.output or "")
        and bad5.exit_code != 0
        and ("No such file" in (bad5.output or "")),
        f"exit={bad5.exit_code} out={(bad5.output or '')[:60]!r}",
    )

    # A6. 动态超时：管理员 PUT 设置 → 存量 backend 调用时读取 → 卡死命令到点击杀
    import pymongo
    from bson import ObjectId  # pymongo>=4.17 不再顶层暴露 ObjectId

    env = _env_map()
    client = pymongo.MongoClient(
        env.get("MONGODB_URL", "mongodb://localhost:27017"),
        username=env.get("MONGODB_USERNAME") or None,
        password=env.get("MONGODB_PASSWORD") or None,
        authSource=env.get("MONGODB_AUTH_SOURCE", "admin"),
        serverSelectionTimeoutMS=3000,
    )
    client[env.get("MONGODB_DB", "agent_state")].users.update_one(
        {"_id": ObjectId(user_id)}, {"$set": {"roles": ["admin", "user"]}}
    )
    # 前端 PUT /api/settings 的落库链路等价于这里的 system_settings 直写；
    # 进程内生效见下方 setattr 注释。
    db = client[env.get("MONGODB_DB", "agent_state")]
    db.system_settings.update_one(
        {"key": "SANDBOX_LOCAL_EXEC_TIMEOUT"},
        {
            "$set": {"value": 4, "updated_by": "e2e"},
            "$setOnInsert": {
                "key": "SANDBOX_LOCAL_EXEC_TIMEOUT",
                "category": "sandbox",
                "type": "number",
                "default_value": 120,
                "description": "settingDesc.SANDBOX_LOCAL_EXEC_TIMEOUT",
            },
        },
        upsert=True,
    )
    # refresh_settings 只对已初始化 settings service 的进程（后端服务进程）生效，
    # E2E 进程内未初始化该 service 是静默 no-op——这里直接改本进程 settings 单例，
    # 验证目标正是 _exec_timeout_now() 每次 aexecute 现读 settings 的「调用时读取」。
    from src.kernel.config import settings as live_settings

    live_settings.SANDBOX_LOCAL_EXEC_TIMEOUT = 4

    t0 = time.monotonic()
    resp6 = await backend.aexecute("sleep 999")  # 卡死命令：无显式超时，走动态设置
    dt6 = time.monotonic() - t0
    timed_out = "timeout" in (resp6.output or "").lower() and resp6.exit_code is None
    check(
        "卡死命令按动态设置自动击杀",
        timed_out and dt6 < 15,
        f"exit={resp6.exit_code} 用时{dt6:.1f}s out={(resp6.output or '')[:50]!r}",
    )
    db.system_settings.update_one({"key": "SANDBOX_LOCAL_EXEC_TIMEOUT"}, {"$set": {"value": 120}})
    live_settings.SANDBOX_LOCAL_EXEC_TIMEOUT = 120
    assert live_settings.SANDBOX_LOCAL_EXEC_TIMEOUT == 120


async def stress(user_id: str, machine_id: str) -> None:
    import random

    from src.infra.sandbox.relay.dispatch import dispatch_local_call

    fast_cmd = "echo ok-$(date +%s%N | tail -c 5)"
    medium_cmd = "seq 1 2000 | sha256sum | head -c 24"
    slow_cmd = "sleep 1.5 && echo slow-done"

    async def one(rnd: random.Random):
        roll = rnd.random()
        cmd = fast_cmd if roll < 0.7 else (medium_cmd if roll < 0.9 else slow_cmd)
        t0 = time.monotonic()
        try:
            r = await dispatch_local_call(
                user_id, "exec", {"command": cmd, "cwd": "/workspace/e2e"}, machine_id=machine_id
            )
            ok = r.get("status") == "ok" and r.get("exit_code") == 0
            detail = "" if ok else str(r.get("error"))[:120]
            return ok, (time.monotonic() - t0) * 1000, detail
        except Exception as exc:  # noqa: BLE001
            return False, (time.monotonic() - t0) * 1000, f"{type(exc).__name__}: {exc}"[:120]

    for conc in (1, 5, 10, 20):
        sink: list = []
        t0 = time.monotonic()

        async def worker(i: int):
            rnd = random.Random(i)
            for _ in range(10):
                sink.append(await one(rnd))

        await asyncio.gather(*(worker(i) for i in range(conc)))
        ms = sorted(x[1] for x in sink)
        ok = sum(1 for x in sink if x[0])
        fails = {x[2] for x in sink if not x[0]}
        check(
            f"压测 并发={conc}",
            ok == len(sink),
            f"{len(sink)} 调用 {ok} 成功 rps={len(sink) / (time.monotonic() - t0):.1f} "
            f"p50={ms[len(ms) // 2]:.0f}ms max={ms[-1]:.0f}ms"
            + (f" 失败原因={fails}" if fails else ""),
        )

    sink = []
    deadline = time.monotonic() + 20

    async def sw(i: int):
        rnd = random.Random(1000 + i)
        while time.monotonic() < deadline:
            sink.append(await one(rnd))

    t0 = time.monotonic()
    await asyncio.gather(*(sw(i) for i in range(20)))
    ok = sum(1 for x in sink if x[0])
    ms = sorted(x[1] for x in sink)
    fails = {x[2] for x in sink if not x[0]}
    check(
        "压测 持续 20 并发×20s",
        ok == len(sink),
        f"{len(sink)} 调用 rps={len(sink) / (time.monotonic() - t0):.1f} "
        f"p50={ms[len(ms) // 2]:.0f}ms p99={ms[int(len(ms) * 0.99)]:.0f}ms"
        + (f" 失败原因={fails}" if fails else ""),
    )


async def run_daemon_child(pat: str, machine_id: str) -> None:
    sys.path.insert(0, str(REPO / "client"))
    from lambchat_sandbox.config import SandboxConfig
    from lambchat_sandbox.daemon import run_daemon

    ws = WORKSPACE_ROOT / machine_id / "workspaces"
    ws.mkdir(parents=True, exist_ok=True)
    cfg = SandboxConfig(
        server_url=SERVER,
        data_root=ws,
        confirm_policy="all",
        machine_id=machine_id,
        machine_name="E2E-AUTO",
    )
    await run_daemon(cfg, pat=pat)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--stress", action="store_true", help="追加压测段")
    ap.add_argument("--daemon-child", nargs=2, metavar=("PAT", "MACHINE_ID"))
    args = ap.parse_args()

    if args.daemon_child:
        try:
            asyncio.run(run_daemon_child(args.daemon_child[0], args.daemon_child[1]))
        except (KeyboardInterrupt, asyncio.CancelledError):
            pass
        return 0

    backend = ensure_backend()
    machine_id = f"e2e-{int(time.time())}-{secrets.token_hex(3)}"
    username = f"sbx-e2e-{secrets.token_hex(4)}"
    password = f"E2e-{secrets.token_hex(8)}!"
    daemon = None
    try:
        pat, jwt = mint_pat(username, password)
        _, me = http_json("GET", "/api/auth/me", token=jwt)  # /me 认 JWT，PAT 只用于沙箱端点
        user_id = me.get("id") or me.get("user", {}).get("id")
        _PAT_HOLDER["pat"] = pat
        holder = {"proc": spawn_daemon(pat, machine_id)}
        print(f"[env] daemon pid={holder['proc'].pid} machine={machine_id} user={username}")

        async def run_all():
            # battery/edge/crash/stress 必须同一事件循环：redis 客户端是模块级单例，
            # 跨 asyncio.run 复用会把旧循环的连接带进新循环（Event loop is closed）
            await battery(user_id, pat, machine_id)
            await edge_cases(user_id, machine_id)
            await crash_recovery(user_id, pat, machine_id, holder)
            await comprehensive(user_id, pat, machine_id, holder)
            await agent_tools_battery(user_id, pat, machine_id)
            if args.stress:
                await stress(user_id, machine_id)

        asyncio.run(run_all())
        daemon = holder["proc"]
        # 优雅下线：SIGTERM → 3s 内 machines 翻转离线（post_offline 定向注销）
        daemon.send_signal(signal.SIGTERM)
        daemon.wait(timeout=10)
        offline_fast = False
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            _, machines = http_json("GET", "/api/sandbox/machines", token=pat)
            m = next((x for x in machines["machines"] if x["machine_id"] == machine_id), None)
            if m and not m["online"]:
                offline_fast = True
                break
            time.sleep(0.3)
        check("优雅下线 5s 内翻转离线", offline_fast)
    finally:
        if daemon and daemon.poll() is None:
            daemon.terminate()
        if backend:
            backend.terminate()
        shutil.rmtree(WORKSPACE_ROOT / machine_id, ignore_errors=True)
        cleanup_user(username)

    fails = [r for r in _results if not r[1]]
    print(f"\n===== E2E 汇总：{len(_results) - len(fails)}/{len(_results)} PASS =====")
    for name, _, note in fails:
        print(f"  FAIL: {name} {note}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
