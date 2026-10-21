#!/usr/bin/env python3
"""I1-I12: real storage, private access, and deployed desktop/mobile image loading."""

import base64
import hashlib
import json
import os
import struct
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
import zlib
from pathlib import Path

import disttest as common

common.RESULTS = os.environ.get("DISTTEST_IMAGE_RESULTS", common.RESULTS)
DIR = Path(__file__).resolve().parent
CLEANUP = {}


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


OPENER = urllib.request.build_opener(NoRedirect())


def request(method, url, token=None, data=None, headers=None):
    headers = dict(headers or {})
    if token:
        headers["Authorization"] = "Bearer " + token
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        response = OPENER.open(req, timeout=40)
    except urllib.error.HTTPError as exc:
        response = exc
    with response:
        return response.status, {k.lower(): v for k, v in response.headers.items()}, response.read()


def api(method, path, token, body=None):
    data = json.dumps(body).encode() if body is not None else None
    status, _, payload = request(
        method, common.NP + path, token, data, {"Content-Type": "application/json"}
    )
    assert status == 200, f"{method} {path.split('?')[0]} returned {status}"
    return json.loads(payload)


def pod_python(source):
    proc = subprocess.run(
        [
            "k3s",
            "kubectl",
            "exec",
            "-i",
            "-n",
            "lambchat",
            "deploy/lambchat-a",
            "--",
            "/app/.venv/bin/python",
            "-",
        ],
        input=source,
        text=True,
        capture_output=True,
        timeout=60,
    )
    assert proc.returncode == 0, "image fixture setup in API pod failed"
    return json.loads(proc.stdout.strip().splitlines()[-1])


def unique_png(marker):
    def chunk(kind, body):
        return (
            struct.pack(">I", len(body))
            + kind
            + body
            + struct.pack(">I", zlib.crc32(kind + body) & 0xFFFFFFFF)
        )

    width, height = 1280, 720
    row = bytes((52, 130, 176)) * width
    rows = bytearray((b"\0" + row) * height)
    rows[1:49] = uuid.UUID(marker).bytes * 3
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(rows))
        + chunk(b"IEND", b"")
    )


def prepare_fixture(session_prefix="部署回归｜图片直连与私有鉴权｜"):
    marker = str(uuid.uuid4())
    sid = str(uuid.uuid4())
    CLEANUP["session"] = sid
    common.remember_session(sid)
    png = unique_png(marker)
    fixture = pod_python(
        """import asyncio,base64,io,json
from datetime import timedelta
from bson import ObjectId
from src.infra.auth.jwt import create_access_token
from src.infra.session.storage import SessionStorage
from src.kernel.schemas.session import SessionCreate
from src.infra.user.storage import UserStorage
from src.infra.storage.s3.service import get_or_init_storage
from src.infra.agent.events.binary_uploads import _upload_private_screenshot
async def main():
 users=UserStorage(); owner=await users.get_by_id(OWNER);assert owner and owner.is_active
 other=await users.collection.find_one({"_id":{"$ne":ObjectId(OWNER)},"is_active":True},{"_id":1});assert other
 await SessionStorage().create(SessionCreate(name=PREFIX+MARKER,metadata={"agent_id":"quick"}),OWNER,session_id=SESSION)
 raw=base64.b64decode(PNG);storage=await get_or_init_storage()
 capture=await _upload_private_screenshot(storage,io.BytesIO(raw),"image-regression-private.png","image/png",len(raw),OWNER,SESSION)
 print(json.dumps({"token":create_access_token(OWNER,expires_delta=timedelta(minutes=15)),"other_token":create_access_token(str(other["_id"]),expires_delta=timedelta(minutes=2)),"private_key":capture.key}))
asyncio.run(main())
""".replace("PREFIX", repr(session_prefix))
        .replace("OWNER", repr(common.UID))
        .replace("MARKER", repr(marker))
        .replace("SESSION", repr(sid))
        .replace("PNG", repr(base64.b64encode(png).decode()))
    )
    CLEANUP.update(session=sid, private_key=fixture["private_key"], token=fixture["token"])
    token = fixture["token"]
    assert api("GET", "/api/auth/me", token)["id"] == common.UID
    assert api("GET", "/api/auth/me", fixture["other_token"])["id"] != common.UID
    boundary = "image-regression-" + marker
    name = "image-regression-" + marker + ".png"
    upload_body = (
        f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="{name}"\r\nContent-Type: image/png\r\n\r\n'.encode()
        + png
        + f"\r\n--{boundary}--\r\n".encode()
    )
    status, _, raw = request(
        "POST",
        common.NP + "/api/upload/file",
        token,
        upload_body,
        {"Content-Type": "multipart/form-data; boundary=" + boundary},
    )
    assert status == 200, f"image upload returned {status}"
    file = json.loads(raw)
    CLEANUP["public_key"] = file["key"]
    public_url = common.PUB + "/api/upload/file/" + file["key"]
    storage_host = None
    for number, flags, label in [
        (1, "", "原图"),
        (2, "?thumb=1", "缩略图"),
        (3, "?cover=1", "封面"),
    ]:
        status, headers, _ = request("GET", public_url + flags)
        assert status == 302, f"{label} direct URL must redirect to storage, got {status}"
        signed = headers["location"]
        parsed = urllib.parse.urlsplit(signed)
        assert parsed.scheme == "https" and parsed.hostname
        storage_host = parsed.hostname
        status, direct_headers, direct = request("GET", signed)
        assert status == 200 and direct_headers.get("content-type", "").startswith("image/"), (
            f"{label} storage response invalid"
        )
        proxy_url = public_url + (flags + "&proxy=true" if flags else "?proxy=true")
        status, proxy_headers, proxied = request("GET", proxy_url)
        assert status == 200 and "location" not in proxy_headers, (
            f"{label} proxy must stream bytes, got {status}"
        )
        assert proxy_headers.get("content-type", "").startswith("image/") and proxied == direct
        if not flags:
            assert hashlib.sha256(proxied).digest() == hashlib.sha256(png).digest()
        common.record(
            f"I{number}-图片{label}直连与代理",
            True,
            f"storage302→200; proxy200/no redirect; bytes={len(proxied)}",
        )
    private_url = common.PUB + "/api/upload/file/" + fixture["private_key"]
    variants = ["", "?thumb=1", "?cover=1&proxy=true", "?thumb=1&proxy=true", "?direct=true"]
    for flags in variants:
        status, headers, data = request("GET", private_url + flags, token)
        assert status == 200 and data and headers.get("content-type", "").startswith("image/")
        assert "no-store" in headers.get("cache-control", "") and "location" not in headers
    common.record("I4-私有图片本人鉴权读取", True, "5组参数均返回图片/no-store/无存储重定向")
    for number, who, actor in [(5, "匿名", None), (6, "其他有效账号", fixture["other_token"])]:
        for flags in variants:
            status, headers, _ = request(
                "GET", common.NP + "/api/upload/file/" + fixture["private_key"] + flags, actor
            )
            assert status == 404 and "location" not in headers, (
                f"private image {who} {flags} returned {status}"
            )
        common.record(f"I{number}-私有图片拒绝{who}", True, "5组参数均404；未生成存储访问链接")
    public_alt = "regression-public-" + marker
    private_alt = "regression-private-" + marker
    message = f"图片展示回归，勿访问链接或调用工具，只回复 IMAGE_UI_OK。\n\n![{public_alt}]({public_url})\n\n![{private_alt}](/api/upload/file/{fixture['private_key']})"
    run = api(
        "POST",
        "/api/chat/stream?agent_id=quick",
        token,
        {"session_id": sid, "message": message, "agent_options": {"model": common.FLASH}},
    )
    deadline = time.monotonic() + 120
    while time.monotonic() < deadline:
        state = api("GET", f"/api/chat/sessions/{sid}/status?run_id={run['run_id']}", token)[
            "status"
        ]
        if state not in {"pending", "queued", "starting", "running", "recovering"}:
            break
        time.sleep(1)
    assert state == "completed", f"image fixture chat ended {state}"
    metadata = {
        "base": common.PUB,
        "session": sid,
        "token": token,
        "publicKey": file["key"],
        "privateKey": fixture["private_key"],
        "publicAlt": public_alt,
        "privateAlt": private_alt,
        "storageHost": storage_host,
    }
    return metadata


def main():
    metadata = prepare_fixture()
    proc = subprocess.Popen(
        ["node", str(DIR / "image-loading-browser.mjs")],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        out, _ = proc.communicate(json.dumps(metadata), timeout=420)
    except subprocess.TimeoutExpired:
        proc.terminate()
        try:
            proc.communicate(timeout=15)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.communicate()
        raise RuntimeError("image browser regression timed out") from None
    results = [json.loads(line) for line in out.splitlines() if line.startswith("{")]
    for result in results:
        common.record(result["test"], result["ok"], result["detail"])
    assert proc.returncode == 0 and len(results) == 6 and all(r["ok"] for r in results), (
        "deployed image browser regression failed or incomplete"
    )


def cleanup_images():
    if "public_key" in CLEANUP:
        api("DELETE", "/api/upload/" + CLEANUP["public_key"], CLEANUP["token"])
    if "private_key" in CLEANUP:
        pod_python(
            'import asyncio,json\nfrom src.infra.storage.s3.service import get_or_init_storage\nfrom src.infra.upload.file_record import FileRecordStorage\nasync def main():\n records=FileRecordStorage();record=await records.find_by_key(KEY)\n assert record and record.get("private_session_id")==SESSION and record["name"]=="image-regression-private.png"\n storage=await get_or_init_storage();await storage.delete_file(KEY);await records.delete_by_key(KEY,record["uploaded_by"])\n print(json.dumps({"cleaned":True}))\nasyncio.run(main())\n'.replace(
                "KEY", repr(CLEANUP["private_key"])
            ).replace("SESSION", repr(CLEANUP["session"]))
        )


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        common.record("I0-图片回归未完成", False, f"{type(exc).__name__}: {str(exc)[:220]}")
        raise SystemExit(1) from None
    finally:
        try:
            cleanup_images()
        except Exception as exc:
            common.record("I0-图片测试产物清理", False, type(exc).__name__ + ": cleanup failed")
            raise SystemExit(1) from None
