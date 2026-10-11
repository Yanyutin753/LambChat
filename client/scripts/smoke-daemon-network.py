import json
import os
import subprocess
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

connected = threading.Event()
release = threading.Event()


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.end_headers()
        self.wfile.write(b'event: hello\ndata: {"client_id":"packaging-smoke"}\n\n')
        self.wfile.flush()
        connected.set()
        release.wait(20)

    def do_POST(self):
        self.rfile.read(int(self.headers.get("Content-Length", 0)))
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"{}")

    def log_message(self, *args):
        pass


server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
threading.Thread(target=server.serve_forever, daemon=True).start()
with tempfile.TemporaryDirectory(prefix="lambchat-network-smoke-") as temp:
    root = Path(temp)
    origin = f"http://127.0.0.1:{server.server_port}"
    (root / "sandbox.json").write_text(json.dumps({"server_url": origin, "embedded_python": False}))
    (root / "pat").write_text(json.dumps({"origin": origin, "token": "packaging-smoke-fake-pat"}))
    env = dict(os.environ, LAMBCHAT_HOME=temp, PYTHONUNBUFFERED="1")
    with (root / "daemon.log").open("w+") as log:
        proc = subprocess.Popen(
            [str(Path(sys.argv[1]).resolve()), "run"], env=env, stdout=log, stderr=log
        )
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
