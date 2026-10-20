"""An authenticated loopback Qdrant process owned by one validation run."""

import asyncio
import json
import os
import secrets
import socket
import subprocess
import tempfile
from contextlib import asynccontextmanager
from pathlib import Path

import httpx


def capacity_qdrant_binary(scale):
    if scale <= 20000:
        return None
    value = os.environ.get("LAMBCHAT_MEMORY_QDRANT_BINARY")
    path = Path(value).expanduser().resolve() if value else None
    root = Path(__file__).resolve().parents[3]
    if path is None or root in path.parents or not path.is_file() or not os.access(path, os.X_OK):
        raise ValueError("Large capacity evaluation requires an external Qdrant server binary")
    return path


@asynccontextmanager
async def isolated_qdrant(binary, output):
    with tempfile.TemporaryDirectory(prefix="memory-qdrant-", dir=output) as directory:
        path = Path(directory)
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        key = secrets.token_hex(32)
        config = path / "config.yaml"
        config.write_text(
            json.dumps(
                {
                    "telemetry_disabled": True,
                    "service": {
                        "host": "127.0.0.1",
                        "http_port": port,
                        "grpc_port": None,
                        "api_key": key,
                        "max_workers": 1,
                    },
                    "storage": {
                        "storage_path": str(path / "storage"),
                        "snapshots_path": str(path / "snapshots"),
                        "performance": {"max_search_threads": 1},
                        "optimizers": {"max_optimization_threads": 1},
                        "hnsw_index": {"max_indexing_threads": 1},
                    },
                }
            )
        )
        config.chmod(0o600)
        env = {name: value for name, value in os.environ.items() if not name.startswith("QDRANT__")}
        with (output / "qdrant.log").open("x") as log:
            os.chmod(log.name, 0o600)
            process = subprocess.Popen(
                [str(binary), "--config-path", str(config)],
                cwd=path,
                env=env,
                stdout=log,
                stderr=subprocess.STDOUT,
            )
            try:
                url = f"http://127.0.0.1:{port}"
                async with httpx.AsyncClient(timeout=1) as http:
                    async with asyncio.timeout(30):
                        while True:
                            if process.poll() is not None:
                                raise RuntimeError("Isolated Qdrant failed to start")
                            try:
                                response = await http.get(url + "/", headers={"api-key": key})
                                if response.status_code == 200:
                                    break
                            except httpx.TransportError:
                                pass
                            await asyncio.sleep(0.1)
                yield url, key
            finally:
                if process.poll() is None:
                    process.terminate()
                    try:
                        await asyncio.to_thread(process.wait, timeout=10)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        await asyncio.to_thread(process.wait)
