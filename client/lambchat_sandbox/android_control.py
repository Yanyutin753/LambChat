"""Private native Android control bridge; uses the existing approved CUA dispatch."""

from __future__ import annotations

import json
import os
import socket
from pathlib import Path


def request(op: str, payload: dict) -> dict:
    path = Path(os.environ.get("LAMBCHAT_HOME", "/lambchat")) / "phone-bridge.json"
    config = json.loads(path.read_text())
    if config.get("host") != "127.0.0.1":
        raise ValueError("phone bridge must be loopback")
    port, token = config.get("port"), config.get("token")
    if not isinstance(port, int) or not 1 <= port <= 65535:
        raise ValueError("invalid phone bridge port")
    if not isinstance(token, str) or len(token) != 64:
        raise ValueError("invalid phone bridge token")
    encoded = json.dumps({"token": token, "op": op, "payload": payload}).encode() + b"\n"
    if len(encoded) > 65536:
        raise ValueError("phone request too large")
    with socket.create_connection(("127.0.0.1", port), timeout=25) as connection:
        connection.sendall(encoded)
        with connection.makefile("rb") as response:
            line = response.readline(2_000_001)
    if not line.endswith(b"\n") or len(line) > 2_000_000:
        raise ValueError("invalid phone response")
    result = json.loads(line)
    if not isinstance(result, dict):
        raise ValueError("invalid phone result")
    return result


def handle(op: str, payload: dict) -> dict:
    try:
        return request(op, payload)
    except (OSError, ValueError, KeyError) as exc:
        return {"error": "phone_control_unavailable", "detail": str(exc)}
