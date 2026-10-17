"""Real HTTP/model smoke test in an isolated Mongo database and owned Redis process.

Run with scripts/run_validation.py uv run python scripts/e2e_conversation_schedules.py.
Requires local MongoDB, configured working model credentials, and redis-server.
Use --backend arq to also exercise a fresh embedded arq worker.
Only model/settings configuration is copied; no existing conversations or users.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import secrets
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timedelta, timezone
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
            f"apple-{secrets.token_hex(4)}",
            f"pear-{secrets.token_hex(4)}",
        )
        first = await chat(
            f"Remember this sample label for our conversation: {first_token}. Reply only OK."
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
                        "message": f"Remember this sample label for future messages in this conversation: {first_token}. "
                        f"Reply only with {first_token}. Do not call tools."
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
                    assert record["session_id"] != session_id
                    return record
                await asyncio.sleep(1)
            raise AssertionError("Scheduled record was not finalized")

        async def assistant_text(run_id):
            from src.infra.channel.delivery import extract_delivery_text

            record = db.task_run_records.find_one({"_id": run_id})
            assert record and record["session_id"] != session_id
            traces = list(db.traces.find({"session_id": record["session_id"], "run_id": run_id}))
            events = [event for trace in traces for event in trace.get("events", [])]
            assert events, "No persisted real model events"
            assert not any(event["event_type"] == "user:message" for event in events)
            assert any(event["event_type"] == "scheduled:instruction" for event in events)
            return extract_delivery_text(events, max_chars=20000)

        async def delivered_result(run_id):
            response = await api("GET", f"/api/sessions/{session_id}/events?run_id={run_id}")
            results = [
                event for event in response["events"] if event["event_type"] == "scheduled:result"
            ]
            assert len(results) == 1, "The parent must receive exactly one separate result"
            assert not any(event["event_type"] == "user:message" for event in response["events"])
            return results[0]["data"]

        task_a = await create_task("Independent task history A")
        run_a = await api("POST", f"/api/scheduled-tasks/{task_a['id']}/run")
        await wait_task(task_a["id"], run_a["run_id"])
        assert first_token in await assistant_text(run_a["run_id"])
        assert first_token in (await delivered_result(run_a["run_id"]))["content"]
        print("PASS independent task history and result-only parent delivery", flush=True)

        # Only the task's own history can supply this token on its next run.
        await api(
            "PUT",
            f"/api/scheduled-tasks/{task_a['id']}",
            {
                "input_payload": {
                    "message": "What is the sample label I asked you to remember earlier in this conversation? "
                    "Reply only with the label. Do not call tools."
                }
            },
        )
        task_b_label = f"plum-{secrets.token_hex(4)}"
        task_b = await create_task(
            "Independent task history B",
            input_payload={
                "message": f"Remember this sample label for future messages in this conversation: {task_b_label}. "
                f"Reply only with {task_b_label}. Do not call tools."
            },
        )
        human = await api(
            "POST",
            "/api/chat/stream?agent_id=quick",
            {
                "session_id": session_id,
                "message": f"For our conversation, replace the sample label with {second_token}. "
                f"Reply only with {second_token}. Do not call tools.",
            },
        )
        triggers = await asyncio.gather(
            *[api("POST", f"/api/scheduled-tasks/{task['id']}/run") for task in (task_a, task_b)]
        )
        await wait_run(session_id, human["run_id"])
        records = await asyncio.gather(
            *[
                wait_task(task["id"], trigger["run_id"])
                for task, trigger in zip((task_a, task_b), triggers)
            ]
        )
        for trigger, expected_label in zip(triggers, (first_token, task_b_label)):
            text = await assistant_text(trigger["run_id"])
            assert expected_label in text and second_token not in text
            await delivered_result(trigger["run_id"])
        assert records[0]["session_id"] != records[1]["session_id"]
        current = await api("GET", f"/api/sessions/{session_id}")
        assert current["name"] == original["name"]
        assert current["metadata"]["current_run_id"] == human["run_id"]
        assert not current["metadata"].get("hidden_from_conversation_list")
        assert not current["metadata"].get("scheduled_task_id")
        print("PASS concurrent human chat and independent task contexts do not mix", flush=True)

        db.sessions.update_one(
            {"session_id": session_id}, {"$set": {"metadata.task_status": "waiting_human"}}
        )
        one_shot = await create_task(
            "Independent one-shot",
            trigger_type="date",
            trigger_config={
                "run_date": (datetime.now(timezone.utc) + timedelta(seconds=3)).isoformat()
            },
        )
        deadline = time.monotonic() + 200
        while time.monotonic() < deadline:
            pending = await api("GET", f"/api/scheduled-tasks/{one_shot['id']}/runs")
            if pending["items"]:
                await wait_task(one_shot["id"], pending["items"][0]["id"])
                break
            await asyncio.sleep(1)
        else:
            raise AssertionError("One-shot did not trigger while parent was busy")
        current = await api("GET", f"/api/sessions/{session_id}")
        assert current["metadata"]["task_status"] == "waiting_human"
        assert current["metadata"]["current_run_id"] == human["run_id"]
        db.sessions.update_one(
            {"session_id": session_id}, {"$set": {"metadata.task_status": "completed"}}
        )
        print("PASS one-shot executes without changing a busy parent", flush=True)

        clock = await create_task(
            "Real minute clock",
            trigger_config={"seconds": 60},
            timezone="Asia/Shanghai",
            run_on_start=True,
            input_payload={
                "message": "Do not call tools. Reply exactly CLOCK_OK followed by the "
                "system-provided run timestamp in YYYY-MM-DD HH:MM:SS format. "
                "Copy the run time, never calculate it from history.",
                "user_timezone": "Asia/Shanghai",
            },
        )
        deadline = time.monotonic() + 200
        while time.monotonic() < deadline:
            minute_runs = list(
                db.task_run_records.find({"task_id": clock["id"]}).sort("created_at", 1)
            )
            if len(minute_runs) >= 2:
                break
            await asyncio.sleep(1)
        else:
            raise AssertionError("Two real minute firings were not recorded")
        spacing = (minute_runs[1]["created_at"] - minute_runs[0]["created_at"]).total_seconds()
        assert abs(spacing - 60) < 2, f"Minute trigger drift: {spacing}s"
        import re

        for record in minute_runs[:2]:
            await wait_task(clock["id"], record["_id"])
            text = await assistant_text(record["_id"])
            trace = db.traces.find_one(
                {"session_id": record["session_id"], "run_id": record["_id"]}
            )
            instruction = next(
                e["data"]["content"]
                for e in trace["events"]
                if e["event_type"] == "scheduled:instruction"
            )
            timestamp = re.search(
                r"User message sent at: (\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})", instruction
            )
            assert timestamp and timestamp.group(1) in text, (
                "Model did not report the real injected clock"
            )
            result = await delivered_result(record["_id"])
            assert result["timestamp"]
        await api("POST", f"/api/scheduled-tasks/{clock['id']}/pause")
        print(
            f"PASS real minute cadence ({spacing:.3f}s) and model replies copy real run time",
            flush=True,
        )

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
        assert (
            db.traces.count_documents({"session_id": session_id, "run_id": quiet_run["run_id"]})
            == 0
        )
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


async def exercise_unlimited(base_url, db, username, password):
    """Exercise old deadlines and independent execution modes with real models."""
    async with httpx.AsyncClient(base_url=base_url, timeout=30) as client:

        async def api(method, path, body=None):
            response = await client.request(method, path, json=body)
            response.raise_for_status()
            return response.json()

        login = await api("POST", "/api/auth/login", {"username": username, "password": password})
        client.headers["Authorization"] = f"Bearer {login['access_token']}"
        session = await api(
            "POST",
            "/api/sessions",
            {
                "name": "Unlimited execution check",
                "metadata": {"agent_id": "quick", "task_status": "completed"},
            },
        )
        session_id = session["id"]
        runs = []
        for index, mode in enumerate(("conversation", "conversation", "standalone")):
            task = await api(
                "POST",
                "/api/scheduled-tasks/",
                {
                    "name": f"Unlimited {mode} {index}",
                    "agent_id": "quick",
                    "execution_mode": mode,
                    "target_session_id": session_id if mode == "conversation" else None,
                    "source_session_id": session_id,
                    "trigger_type": "interval",
                    "trigger_config": {"seconds": 3600},
                    "timeout_seconds": 10,
                    "input_payload": {
                        "message": "Write 200 numbered short Chinese sentences about trees. End with UNLIMITED_OK."
                    },
                },
            )
            assert task["timeout_seconds"] == 0
            run = await api("POST", f"/api/scheduled-tasks/{task['id']}/run")
            runs.append((task["id"], run["run_id"], mode))
            if len(runs) == 1:
                deadline = time.monotonic() + 30
                while time.monotonic() < deadline:
                    record = db.task_run_records.find_one({"_id": run["run_id"]})
                    if record and record.get("conversation_state") == "submitted":
                        db.task_run_records.update_one(
                            {"_id": run["run_id"]},
                            {
                                "$set": {
                                    "started_at": datetime.now(timezone.utc) - timedelta(days=3),
                                    "timeout_seconds": 10,
                                }
                            },
                        )
                        break
                    await asyncio.sleep(0.1)
                else:
                    raise AssertionError("Conversation run was not submitted")

        traces = []
        for task_id, run_id, mode in runs:
            deadline = time.monotonic() + 600
            while time.monotonic() < deadline:
                response = await api("GET", f"/api/scheduled-tasks/{task_id}/runs")
                record = next((item for item in response["items"] if item["id"] == run_id), None)
                if record and record["status"] in {"success", "failed", "timeout"}:
                    assert record["status"] == "success", record
                    trace = db.traces.find_one(
                        {"session_id": record["session_id"], "run_id": run_id}
                    )
                    assert trace and trace.get("completed_at"), "Missing completed real model trace"
                    elapsed = (trace["completed_at"] - trace["started_at"]).total_seconds()
                    assert elapsed > 1, (
                        f"Model run too short to exercise sustained execution: {elapsed}"
                    )
                    traces.append((mode, trace))
                    print(
                        f"PASS {mode} unlimited real model completed in {elapsed:.1f}s", flush=True
                    )
                    break
                await asyncio.sleep(1)
            else:
                raise AssertionError("Unlimited scheduled model run did not finish")
            await api("POST", f"/api/scheduled-tasks/{task_id}/pause")
        ordered = sorted(
            [trace for mode, trace in traces if mode == "conversation"],
            key=lambda item: item["started_at"],
        )
        assert len({trace["session_id"] for trace in ordered}) == 2
        assert all(trace["session_id"] != session_id for trace in ordered)
        print("PASS aged legacy deadline ignored and task sessions remain independent", flush=True)


async def exercise_goal_races(base_url, db, username, password):
    """Real HTTP/model runs: competing humans, Goal cancellation, and stale finalization."""
    async with httpx.AsyncClient(base_url=base_url, timeout=60) as client:
        login = await client.post(
            "/api/auth/login", json={"username": username, "password": password}
        )
        login.raise_for_status()
        client.headers["Authorization"] = f"Bearer {login.json()['access_token']}"
        client.headers["Accept-Language"] = "en"

        async def api(method, path, body=None):
            response = await client.request(method, path, json=body)
            assert response.status_code == 200, f"{method} {path}: HTTP {response.status_code}"
            return response.json()

        async def wait_terminal(session_id, run_id):
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
                    return result["status"]
                await asyncio.sleep(0.5)
            raise AssertionError("Goal/user run did not reach terminal state")

        async def control(action):
            # A human control may contend with the bounded submission lease.
            deadline = time.monotonic() + 30
            while time.monotonic() < deadline:
                response = await client.post(f"/api/chat/sessions/{session_id}/goal/{action}")
                if response.status_code != 409:
                    assert response.status_code == 200, (
                        f"Goal {action}: HTTP {response.status_code}"
                    )
                    return response.json()["goal"]
                await asyncio.sleep(0.1)
            raise AssertionError("Goal control could not acquire admission")

        initial = await api(
            "POST", "/api/chat/stream?agent_id=quick", {"message": "Reply exactly READY."}
        )
        session_id = initial["session_id"]
        assert await wait_terminal(session_id, initial["run_id"]) == "completed"
        replies = await asyncio.gather(
            *[
                client.post(
                    "/api/chat/stream?agent_id=quick",
                    json={
                        "session_id": session_id,
                        "message": f"Verification turn {index}. Write exactly 200 words explaining why message ownership matters.",
                    },
                )
                for index in range(3)
            ]
        )
        accepted = [reply.json() for reply in replies if reply.status_code == 200]
        assert len(accepted) == 1, f"Concurrent humans admitted {len(accepted)} runs"
        assert all(reply.status_code in {200, 409} for reply in replies)
        assert await wait_terminal(session_id, accepted[0]["run_id"]) == "completed"
        user_turns = [
            event
            for trace in db.traces.find({"session_id": session_id})
            for event in trace.get("events", [])
            if event["event_type"] == "user:message"
        ]
        assert len(user_turns) == 2, "Rejected submissions leaked user messages into history"
        print(
            "PASS competing real human submissions admit exactly one run and one user message",
            flush=True,
        )

        created = (
            await api(
                "PUT",
                f"/api/chat/sessions/{session_id}/goal",
                {
                    "objective": "Compute 147 times 293 with a tool, then verify the result independently.",
                    "rubric": "The calculation and independent verification must be supported by tool evidence.",
                },
            )
        )["goal"]
        paused = await control("pause")
        assert paused["status"] == "paused" and paused["version"] > created["version"]
        resumed = await control("resume")
        assert resumed["status"] == "active"
        repeated = await control("resume")
        assert repeated["version"] == resumed["version"], "Repeated resume superseded its own run"
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            current = (await api("GET", f"/api/chat/sessions/{session_id}/goal"))["goal"]
            if current.get("current_run_id") and current.get("intent_submitted"):
                break
            await asyncio.sleep(0.2)
        else:
            raise AssertionError("Resumed Goal never admitted a real automatic turn")
        automatic_run_id = current["current_run_id"]
        paused = await control("pause")
        assert paused["status"] == "paused"
        assert paused["current_run_id"] is None
        await wait_terminal(session_id, automatic_run_id)
        human = await api(
            "POST",
            "/api/chat/stream?agent_id=quick",
            {
                "session_id": session_id,
                "message": "Reply exactly HUMAN_AFTER_PAUSE.",
            },
        )
        assert await wait_terminal(session_id, human["run_id"]) == "completed"
        await asyncio.sleep(6)
        final = (await api("GET", f"/api/chat/sessions/{session_id}/goal"))["goal"]
        session = await api("GET", f"/api/sessions/{session_id}")
        assert final["status"] == "paused" and final["version"] == paused["version"]
        assert session["metadata"]["current_run_id"] == human["run_id"]
        assert session["metadata"]["task_status"] == "completed"
        assert session["metadata"].get("task_error_code") != "cancelled"
        goal_events = [
            event
            for trace in db.traces.find({"session_id": session_id, "run_id": automatic_run_id})
            for event in trace.get("events", [])
        ]
        assert any(
            event["event_type"] in {"goal:continuation", "user:message"} for event in goal_events
        )
        assert all(
            event["data"]["content"] == created["objective"]
            for event in goal_events
            if event["event_type"] == "user:message"
        )
        cleared = await control("clear")
        assert cleared["status"] == "cleared"
        assert (await control("resume"))["status"] == "cleared"
        print(
            "PASS real Goal pause/resume/cancel keeps later human state and automatic origin intact",
            flush=True,
        )

        # Replaying durable completion bookkeeping must not re-run models or double-count.
        record = db.task_run_records.find_one(
            {"conversation_state": "finished", "status": "success"}
        )
        if record:
            total = db.task_run_records.count_documents(
                {
                    "task_id": record["task_id"],
                    "status": {"$in": ["success", "failed", "skipped", "timeout"]},
                    "finished_at": {"$ne": None},
                }
            )
            traces_before = db.traces.count_documents(
                {"session_id": record["session_id"], "run_id": record["_id"]}
            )
            db.task_run_records.update_one(
                {"_id": record["_id"]}, {"$set": {"finalization_pending": True}}
            )
            deadline = time.monotonic() + 30
            while time.monotonic() < deadline:
                refreshed = db.task_run_records.find_one({"_id": record["_id"]})
                if not refreshed.get("finalization_pending"):
                    break
                await asyncio.sleep(0.5)
            else:
                raise AssertionError("Durable finalization was not recovered")
            task = db.scheduled_tasks.find_one({"_id": record["task_id"]})
            assert task["total_runs"] == total
            assert (
                db.traces.count_documents(
                    {"session_id": record["session_id"], "run_id": record["_id"]}
                )
                == traces_before
            )
            print(
                "PASS real Mongo completion replay repairs bookkeeping without model replay or double counting",
                flush=True,
            )


async def exercise_live_progress(base_url, db, username, password):
    """Observe independent startup, streaming and completion through the real WebSocket."""
    import json

    from websockets.asyncio.client import connect

    async with httpx.AsyncClient(base_url=base_url, timeout=30) as client:

        async def api(method, path, body=None):
            response = await client.request(method, path, json=body)
            response.raise_for_status()
            return response.json()

        login = await api("POST", "/api/auth/login", {"username": username, "password": password})
        client.headers["Authorization"] = f"Bearer {login['access_token']}"
        parent = await api(
            "POST",
            "/api/sessions",
            {
                "name": "Live isolated scheduled progress",
                "metadata": {"agent_id": "quick", "task_status": "completed"},
            },
        )
        parent_id = parent["id"]
        async with connect(
            base_url.replace("http://", "ws://").replace("https://", "wss://") + "/ws"
        ) as ws:
            await ws.send(json.dumps({"type": "auth", "token": login["access_token"]}))
            assert json.loads(await asyncio.wait_for(ws.recv(), 20))["type"] == "auth:ok"
            task = await api(
                "POST",
                "/api/scheduled-tasks/",
                {
                    "name": "Visible task progress",
                    "agent_id": "quick",
                    "execution_mode": "conversation",
                    "target_session_id": parent_id,
                    "source_session_id": parent_id,
                    "trigger_type": "interval",
                    "trigger_config": {"seconds": 3600},
                    "notification_policy": "always",
                    "input_payload": {
                        "message": "Do not call tools. Write 100 numbered short lines about trees. "
                        "Begin each line with LIVE_TASK. Do not summarize or stop early."
                    },
                },
            )
            human = await api(
                "POST",
                "/api/chat/stream?agent_id=quick",
                {
                    "session_id": parent_id,
                    "message": "Do not call tools. Write 200 numbered short lines about rivers. "
                    "Begin each line with HUMAN_STREAM. Do not summarize or stop early.",
                },
            )
            scheduled = await api("POST", f"/api/scheduled-tasks/{task['id']}/run")
            progress = []
            final = None
            deadline = time.monotonic() + 240
            while time.monotonic() < deadline and final is None:
                event = json.loads(await asyncio.wait_for(ws.recv(), 60))
                data = event.get("data") or {}
                if data.get("session_id") != parent_id or data.get("run_id") != scheduled["run_id"]:
                    continue
                if event.get("type") == "scheduled:progress":
                    progress.append(data)
                elif event.get("type") == "scheduled:result":
                    final = data
            assert final is not None, "No real-time scheduled result was received"
            assert progress and progress[0]["content"] == "", "Missing task startup bubble"
            assert any(item["status"] == "running" and item["content"] for item in progress), (
                "No running text snapshot"
            )
            assert all(item["message_id"] == final["message_id"] for item in progress)
            assert final.get("assistant_identity") and all(
                item.get("assistant_identity") == final["assistant_identity"] for item in progress
            ), "Task identity changed between startup, worker streaming and the final result"
            assert final["message_id"] == f"scheduled-result:{scheduled['run_id']}"
            assert "LIVE_TASK" in final["content"] and "HUMAN_STREAM" not in final["content"]
            current = await api("GET", f"/api/sessions/{parent_id}")
            assert current["metadata"]["current_run_id"] == human["run_id"]
            child = db.task_run_records.find_one({"_id": scheduled["run_id"]})
            assert child["session_id"] != parent_id
            child_trace = db.traces.find_one(
                {"session_id": child["session_id"], "run_id": child["_id"]}
            )
            human_trace = db.traces.find_one({"session_id": parent_id, "run_id": human["run_id"]})
            assert human_trace and child_trace
            if human_trace.get("completed_at"):
                assert child_trace["started_at"] < human_trace["completed_at"], (
                    "Human and task streams did not overlap"
                )
            history = await api(
                "GET", f"/api/sessions/{parent_id}/events?run_id={scheduled['run_id']}"
            )
            assert all(item["event_type"] == "scheduled:result" for item in history["events"])
            await api("POST", f"/api/scheduled-tasks/{task['id']}/pause")
            # The human run is owned by this disposable test, and may still be generating.
            await api("POST", f"/api/chat/sessions/{parent_id}/cancel")
            print(
                f"PASS live startup + {len(progress)} task snapshots + final replacement, with human stream isolated",
                flush=True,
            )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backend", choices=("local", "arq"), default="local")
    parser.add_argument(
        "--browser",
        action="store_true",
        help="Serve the built frontend on the isolated backend for browser regression",
    )
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
        if args.browser:
            db.system_settings.update_one(
                {"_id": "FRONTEND_DEV_URL"}, {"$set": {"value": ""}}, upsert=True
            )
            context_path = log_dir / "browser.json"
            context_path.write_text(
                json.dumps(
                    {
                        "username": username,
                        "password": password,
                        "base_url": f"http://127.0.0.1:{backend_port}",
                    }
                )
            )
            context_path.chmod(0o600)
            print(f"Browser test context: {context_path}", flush=True)
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
                **({"FRONTEND_DEV_URL": ""} if args.browser else {}),
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
            asyncio.run(exercise_unlimited(base_url, db, username, password))
            asyncio.run(exercise_live_progress(base_url, db, username, password))
            asyncio.run(exercise_goal_races(base_url, db, username, password))
            assert (
                "Task exception was never retrieved" not in (log_dir / "backend.log").read_text()
            ), "An interrupted background coroutine was left unobserved"
    finally:
        stop(backend_process)
        stop(redis_process)
        (log_dir / "browser.json").unlink(missing_ok=True)
        client.drop_database(database_name)
        client.close()
        print(f"Diagnostic logs: {log_dir}")
    assert "asyncio.exceptions.CancelledError" not in (log_dir / "backend.log").read_text(), (
        "Application shutdown cancelled its hosting server task"
    )
    if os.name != "nt":
        assert backend_process is not None and backend_process.returncode in {0, -15}, (
            f"Backend did not stop gracefully: {getattr(backend_process, 'returncode', None)}"
        )
    print(f"PASS real HTTP/model smoke ({args.backend}); isolated test data removed")


if __name__ == "__main__":
    main()
