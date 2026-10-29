"""Real daemon process + HTTP/SSE file regression; optional packaged executable."""

import base64
import json
import os
import queue
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

connected = threading.Event()
release = threading.Event()
calls = queue.Queue()
results = queue.Queue()
WORKSPACE_ID = "local-" + "a" * 32


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.end_headers()
        self.wfile.write(b'event: hello\ndata: {"client_id":"packaging-smoke"}\n\n')
        self.wfile.flush()
        connected.set()
        while not release.is_set():
            try:
                call = calls.get(timeout=1)
            except queue.Empty:
                continue
            self.wfile.write(b"event: tool_call\ndata: " + json.dumps(call).encode() + b"\n\n")
            self.wfile.flush()

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
        if self.path.startswith("/api/sandbox/results/") and body.get("stage") == "done":
            results.put((urlsplit(self.path).path.rsplit("/", 1)[-1], body))
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"{}")

    def log_message(self, *args):
        pass


def call_file(op, path, **payload):
    call_id = f"file-{uuid.uuid4().hex}"
    calls.put(
        {
            "call_id": call_id,
            "machine_id": "packaging-smoke",
            "op": op,
            "timeout": 10,
            "payload": {
                "cwd": f"/workspace/.selected/{WORKSPACE_ID}",
                "path": path,
                "versioned": True,
                **payload,
            },
        }
    )
    received_id, body = results.get(timeout=15)
    assert received_id == call_id, (received_id, call_id)
    assert body.get("status") == "ok", body
    return body["result"]


def verify_files(selected, root):
    for name in ("README.md", "pyproject.toml", "frontend/package.json", "中文 文件.txt"):
        first = call_file("fs_read", name, limit=1)
        assert not first.get("error"), (name, first)
        assert first["content"] == "current", first
        assert first.get("version"), first
        tail = call_file("fs_read", name, offset=1, limit=1)
        assert tail.get("content") == "second line", tail
        assert tail.get("version") == first["version"], tail
    print("DAEMON_VERSIONED_READ_PASS", flush=True)

    name = "README.md"
    observed = call_file("fs_read", name)
    target = selected / name
    target.write_bytes(b"external change\n")
    rejected = call_file(
        "fs_edit",
        name,
        expected_version=observed["version"],
        old_str_b64=base64.b64encode(b"current").decode(),
        new_str_b64=base64.b64encode(b"replacement").decode(),
    )
    assert "file_conflict" in rejected.get("error", ""), rejected
    assert target.read_bytes() == b"external change\n"
    current = call_file("fs_read", name)
    assert not current.get("error"), current
    edited = call_file(
        "fs_edit",
        name,
        expected_version=current["version"],
        old_str_b64=base64.b64encode(b"external change").decode(),
        new_str_b64=base64.b64encode(b"replacement").decode(),
    )
    assert not edited.get("error"), edited
    final = call_file("fs_read", name)
    assert final.get("content") == "replacement", final
    assert final.get("version") != current["version"], final
    assert target.read_bytes() == b"replacement\n"
    snapshots = root / "workspaces" / ".file-history" / "snapshots"
    assert any(p.read_bytes() == b"external change\n" for p in snapshots.glob("*.blob"))
    print("DAEMON_STALE_WRITE_AND_RECOVERY_PASS", flush=True)


server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
threading.Thread(target=server.serve_forever, daemon=True).start()
with tempfile.TemporaryDirectory(prefix="lambchat-network-smoke-") as temp:
    root = Path(temp)
    origin = f"http://127.0.0.1:{server.server_port}"
    (root / "sandbox.json").write_text(
        json.dumps(
            {
                "server_url": origin,
                "embedded_python": False,
                "machine_id": "packaging-smoke",
            }
        )
    )
    (root / "pat").write_text(json.dumps({"origin": origin, "token": "packaging-smoke-fake-pat"}))
    selected = root / "selected-中文工作目录"
    selected.mkdir()
    bindings = root / "workspaces" / ".selected"
    bindings.mkdir(parents=True)
    native_path = str(selected.resolve())
    if os.name == "nt" and not native_path.startswith("\\\\"):
        native_path = "\\\\?\\" + native_path
    (bindings / f"{WORKSPACE_ID}.json").write_text(
        json.dumps(native_path, ensure_ascii=False),
        encoding="utf-8",
    )
    for name in ("README.md", "pyproject.toml", "frontend/package.json", "中文 文件.txt"):
        target = selected / name
        target.parent.mkdir(exist_ok=True)
        target.write_bytes(b"initial\n")
        target.write_bytes(b"current\r\nsecond line\r\n")
    env = dict(
        os.environ,
        LAMBCHAT_HOME=temp,
        PYTHONUNBUFFERED="1",
        PYTHONPATH=str(Path(__file__).resolve().parents[1]),
    )
    command = (
        [str(Path(sys.argv[1]).resolve())]
        if len(sys.argv) > 1
        else [sys.executable, "-m", "lambchat_sandbox"]
    )
    with (root / "daemon.log").open("w+", encoding="utf-8") as log:
        proc = subprocess.Popen([*command, "run"], env=env, stdout=log, stderr=log)
        try:
            ok = False
            deadline = time.monotonic() + 10
            while proc.poll() is None and time.monotonic() < deadline:
                if connected.is_set():
                    output = (root / "daemon.log").read_text(encoding="utf-8")
                    if "[sandbox] 已连接" in output and "packaging-smoke" in output:
                        ok = True
                        break
                time.sleep(0.1)
            assert ok, "Daemon did not establish its SSE connection"
            verify_files(selected, root)
        except BaseException:
            log.flush()
            print((root / "daemon.log").read_text(encoding="utf-8"), file=sys.stderr)
            raise
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=12)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()
            release.set()
            server.shutdown()
        if not ok:
            log.seek(0)
            raise AssertionError("Packaged daemon did not connect: " + log.read())
print("PACKAGED_ASYNC_NETWORK_PASS")
