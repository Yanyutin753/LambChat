"""Real HTTP/model smoke test in an isolated Mongo database and owned Redis process.

Run with scripts/run_validation.py uv run python scripts/e2e_conversation_schedules.py.
Requires local MongoDB, configured working model credentials, and redis-server.
Use --backend arq to also exercise a fresh embedded arq worker.
Only model/settings configuration is copied; no existing conversations or users.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import secrets
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from uuid import uuid4

import httpx
from pymongo import MongoClient

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))


def free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def stop(process):
    if process is not None:
        process.terminate()
        try:
            process.wait(timeout=15)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)


async def exercise(base_url, db, username, password):
    async with httpx.AsyncClient(base_url=base_url, timeout=30) as client:

        async def api(method, path, body=None, expected=200):
            response = await client.request(method, path, json=body)
            assert response.status_code == expected, f"{method} {path}: HTTP {response.status_code}"
            return response.json()

        login = await api("POST", "/api/auth/login", {"username": username, "password": password})
        client.headers["Authorization"] = f"Bearer {login['access_token']}"
        client.headers["Accept-Language"] = "en"

        async def wait_run(session_id, run_id):
            deadline = time.monotonic() + 180
            while time.monotonic() < deadline:
                result = await api("GET", f"/api/chat/sessions/{session_id}/status?run_id={run_id}")
                if result["status"] not in {
                    "pending",
                    "queued",
                    "starting",
                    "running",
                    "recovering",
                }:
                    assert result["status"] == "completed", f"Run ended: {result['status']}"
                    return
                await asyncio.sleep(1)
            raise AssertionError("Real model run did not finish within 180 seconds")

        async def chat(message, session_id=None):
            result = await api(
                "POST",
                "/api/chat/stream?agent_id=quick",
                {
                    "message": message,
                    "session_id": session_id,
                },
            )
            await wait_run(result["session_id"], result["run_id"])
            return result

        first_token, second_token = (
            f"FIRST_{secrets.token_hex(4)}",
            f"SECOND_{secrets.token_hex(4)}",
        )
        first = await chat(
            f"Remember the current verification token: {first_token}. Reply only OK."
        )
        session_id = first["session_id"]
        original = await api("GET", f"/api/sessions/{session_id}")

        async def create_task(name, **fields):
            return await api(
                "POST",
                "/api/scheduled-tasks/",
                {
                    "name": name,
                    "agent_id": "quick",
                    "execution_mode": "conversation",
                    "target_session_id": session_id,
                    "source_session_id": session_id,
                    "trigger_type": "interval",
                    "trigger_config": {"seconds": 3600},
                    "notification_policy": "always",
                    "timeout_seconds": 180,
                    "input_payload": {
                        "message": "Reply only with the current verification token from this conversation."
                    },
                    **fields,
                },
                expected=201,
            )

        async def wait_task(task_id, run_id):
            deadline = time.monotonic() + 200
            while time.monotonic() < deadline:
                response = await api("GET", f"/api/scheduled-tasks/{task_id}/runs")
                record = next((item for item in response["items"] if item["id"] == run_id), None)
                if record and record["status"] in {"success", "failed", "timeout", "skipped"}:
                    assert record["status"] == "success", f"Scheduled run ended: {record['status']}"
                    assert record["session_id"] == session_id
                    return record
                await asyncio.sleep(1)
            raise AssertionError("Scheduled record was not finalized")

        async def assistant_text(run_id):
            from src.infra.channel.delivery import extract_delivery_text

            # The public history endpoint must expose the same original-session run.
            response = await api("GET", f"/api/sessions/{session_id}/events?run_id={run_id}")
            assert response
            traces = list(db.traces.find({"session_id": session_id, "run_id": run_id}))
            events = [event for trace in traces for event in trace.get("events", [])]
            assert events, "No persisted real model events"
            return extract_delivery_text(events, max_chars=20000)

        task_a = await create_task("Context check A")
        run_a = await api("POST", f"/api/scheduled-tasks/{task_a['id']}/run")
        await wait_task(task_a["id"], run_a["run_id"])
        assert first_token in await assistant_text(run_a["run_id"])
        print("PASS original conversation history reaches scheduled model run", flush=True)

        await chat(
            f"Replace the current verification token with {second_token}. The old token is obsolete. Reply OK.",
            session_id,
        )
        task_b = await create_task("Context check B")
        triggers = await asyncio.gather(
            *[api("POST", f"/api/scheduled-tasks/{task['id']}/run") for task in (task_a, task_b)]
        )
        records = await asyncio.gather(
            *[
                wait_task(task["id"], trigger["run_id"])
                for task, trigger in zip((task_a, task_b), triggers)
            ]
        )
        for trigger in triggers:
            assert second_token in await assistant_text(trigger["run_id"])
        actual_traces = [
            db.traces.find_one({"session_id": session_id, "run_id": record["id"]})
            for record in records
        ]
        assert all(trace and trace.get("completed_at") for trace in actual_traces)
        ordered = sorted(actual_traces, key=lambda trace: trace["started_at"])
        assert ordered[1]["started_at"] >= ordered[0]["completed_at"], "Scheduled checks overlapped"
        current = await api("GET", f"/api/sessions/{session_id}")
        assert current["name"] == original["name"]
        assert not current["metadata"].get("hidden_from_conversation_list")
        assert not current["metadata"].get("scheduled_task_id")
        print("PASS two schedules serialize and inherit later human context", flush=True)

        # A durable busy-state fixture exercises the real HTTP/DB/scanner path.
        db.sessions.update_one(
            {"session_id": session_id}, {"$set": {"metadata.task_status": "waiting_human"}}
        )
        from datetime import datetime, timedelta, timezone

        one_shot = await create_task(
            "Deferred one-shot",
            trigger_type="date",
            trigger_config={
                "run_date": (datetime.now(timezone.utc) + timedelta(seconds=3)).isoformat(),
            },
        )
        await asyncio.sleep(14)
        pending = await api("GET", f"/api/scheduled-tasks/{one_shot['id']}/runs")
        assert len(pending["items"]) == 1 and pending["items"][0]["status"] == "pending"
        db.sessions.update_one(
            {"session_id": session_id}, {"$set": {"metadata.task_status": "completed"}}
        )
        await wait_task(one_shot["id"], pending["items"][0]["id"])
        print("PASS one-shot survives busy state and executes after release", flush=True)

        quiet = await create_task(
            "Quiet check",
            notification_policy="meaningful_changes",
            input_payload={
                "message": "This check has no changes and needs no action. Reply exactly NO_UPDATE.",
            },
        )
        quiet_run = await api("POST", f"/api/scheduled-tasks/{quiet['id']}/run")
        await wait_task(quiet["id"], quiet_run["run_id"])
        assert (await assistant_text(quiet_run["run_id"])).strip() == "NO_UPDATE"
        assert db.task_completions.count_documents({"data.run_id": quiet_run["run_id"]}) == 0
        print("PASS no-update check persists history without a completion notification", flush=True)

        await api("POST", f"/api/scheduled-tasks/{task_a['id']}/pause")
        result = await api("POST", f"/api/scheduled-tasks/{task_a['id']}/run")
        assert result.get("skipped") is True
        standalone = await create_task(
            "Legacy standalone", execution_mode="standalone", target_session_id=None
        )
        result = await api("POST", f"/api/scheduled-tasks/{standalone['id']}/run")
        deadline = time.monotonic() + 200
        while time.monotonic() < deadline:
            runs = await api("GET", f"/api/scheduled-tasks/{standalone['id']}/runs")
            record = next((item for item in runs["items"] if item["id"] == result["run_id"]), None)
            if record and record["status"] in {"success", "failed", "timeout"}:
                assert record["status"] == "success"
                assert record["session_id"] != session_id
                break
            await asyncio.sleep(1)
        else:
            raise AssertionError("Standalone task did not complete")
        print("PASS pause and standalone compatibility", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backend", choices=("local", "arq"), default="local")
    args = parser.parse_args()
    from src.infra.auth.password import hash_password
    from src.infra.storage.mongodb import build_mongo_connection_string
    from src.kernel.config import settings

    client = MongoClient(build_mongo_connection_string(), serverSelectionTimeoutMS=5000)
    client.admin.command("ping")
    database_name = f"e2e_conversation_{uuid4().hex}"
    assert database_name not in client.list_database_names()
    source = client[settings.MONGODB_DB]
    db = client[database_name]
    redis_binary = shutil.which("redis-server") or str(
        Path.home() / ".local/opt/redis/bin/redis-server"
    )
    assert Path(redis_binary).is_file(), "redis-server must be installed locally"
    backend_process = redis_process = None
    log_dir = Path(tempfile.mkdtemp(prefix="lambchat-conversation-e2e-"))
    try:
        for name in ("model_configs", "system_settings"):
            documents = list(source[name].find())
            if documents:
                db[name].insert_many(documents)
        assert db.model_configs.count_documents({}) > 0, "No local model configuration available"
        for key, value in {
            "TASK_BACKEND": args.backend,
            "LOG_FORMAT": "%(levelname)s %(message)s",
            "ENABLE_SCHEDULED_TASK": True,
            "ENABLE_MEMORY": False,
            "ENABLE_SKILLS": False,
            "LANGFUSE_ENABLED": False,
            "LANGSMITH_TRACING": False,
            "FEISHU_ENABLED": False,
        }.items():
            db.system_settings.update_one({"_id": key}, {"$set": {"value": value}}, upsert=True)
        username, password = f"e2e-{uuid4().hex[:12]}", secrets.token_urlsafe(24)
        db.users.insert_one(
            {
                "username": username,
                "email": f"{username}@example.com",
                "password_hash": hash_password(password),
                "roles": ["admin"],
                "is_active": True,
                "email_verified": True,
            }
        )
        redis_port, backend_port = free_port(), free_port()
        with (
            (log_dir / "redis.log").open("w") as redis_log,
            (log_dir / "backend.log").open("w") as backend_log,
        ):
            redis_process = subprocess.Popen(
                [
                    redis_binary,
                    "--bind",
                    "127.0.0.1",
                    "--port",
                    str(redis_port),
                    "--save",
                    "",
                    "--appendonly",
                    "no",
                ],
                stdout=redis_log,
                stderr=subprocess.STDOUT,
            )
            env = {
                **os.environ,
                "MONGODB_DB": database_name,
                "REDIS_URL": f"redis://127.0.0.1:{redis_port}/0",
                "REDIS_PASSWORD": "",
                "TASK_BACKEND": args.backend,
                "ARQ_EMBEDDED_WORKER": "true",
                "CHECKPOINT_BACKEND": "mongodb",
                "LOG_FORMAT": "%(levelname)s %(message)s",
            }
            backend_process = subprocess.Popen(
                [
                    sys.executable,
                    "-m",
                    "uvicorn",
                    "src.api.main:app",
                    "--host",
                    "127.0.0.1",
                    "--port",
                    str(backend_port),
                ],
                cwd=REPO,
                env=env,
                stdout=backend_log,
                stderr=subprocess.STDOUT,
            )
            base_url = f"http://127.0.0.1:{backend_port}"
            deadline = time.monotonic() + 60
            while time.monotonic() < deadline:
                assert backend_process.poll() is None, (
                    f"Backend exited; inspect {log_dir / 'backend.log'}"
                )
                try:
                    if httpx.get(f"{base_url}/api/version", timeout=1).status_code == 200:
                        break
                except httpx.HTTPError:
                    pass
                time.sleep(1)
            else:
                raise AssertionError(f"Backend not ready; inspect {log_dir / 'backend.log'}")
            asyncio.run(exercise(base_url, db, username, password))
        print(f"PASS real HTTP/model smoke ({args.backend}); isolated test data removed")
    finally:
        stop(backend_process)
        stop(redis_process)
        client.drop_database(database_name)
        client.close()
        print(f"Diagnostic logs: {log_dir}")


if __name__ == "__main__":
    main()
