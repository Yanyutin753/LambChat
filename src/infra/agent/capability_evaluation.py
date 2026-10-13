"""Offline diagnostics and explicitly isolated live Agent evaluation.

Trace documents are supplied by the caller, never resolved through paths/URLs in a
trace. Mechanical assertions inspect recorded events, not a model's claim of success.
"""

from __future__ import annotations

import asyncio
import json
import time
from collections import Counter
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlsplit

import httpx


def load_cases(path: Path) -> dict[str, Any]:
    suite = json.loads(path.read_text())
    if not isinstance(suite, dict) or not suite.get("version") or not suite.get("cases"):
        raise ValueError("case suite requires a version and nonempty cases")
    ids = [case["case_id"] for case in suite["cases"]]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate case ID")
    for case in suite["cases"]:
        if not case.get("assertions"):
            raise ValueError("case requires mechanical assertions")
    return suite


def load_traces(path: Path) -> dict[str, dict[str, Any]]:
    content = path.read_text()
    if path.suffix == ".jsonl":
        records = []
        for number, line in enumerate(content.splitlines(), 1):
            if not line.strip():
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise ValueError(f"invalid trace JSON at line {number}") from exc
    else:
        try:
            records = json.loads(content)
        except json.JSONDecodeError as exc:
            raise ValueError(f"invalid trace JSON at line {exc.lineno}") from exc
        if isinstance(records, dict):
            records = records.get("traces", [records])
    if not isinstance(records, list):
        raise ValueError("trace input must be a list of records")
    indexed = {}
    for record in records:
        if not isinstance(record, dict) or not isinstance(record.get("case_id"), str):
            raise ValueError("trace requires case_id")
        if record["case_id"] in indexed:
            raise ValueError("duplicate trace case ID")
        indexed[record["case_id"]] = record
    return indexed


def empty_result(case: dict[str, Any], outcome: str, stage: str | None) -> dict[str, Any]:
    return {
        "case_id": case["case_id"],
        "outcome": outcome,
        "failure_stage": stage,
        "evidence": [],
        "tokens": {"input": None, "output": None, "total": None},
        "elapsed_seconds": None,
        "tool_calls": 0,
        "duplicate_effects": 0,
    }


def _field(value: dict[str, Any], path: str) -> Any:
    current: Any = value
    for part in path.split("."):
        if not isinstance(current, dict):
            return None
        current = current.get(part)
    return current


def _final_answer(events: list[dict[str, Any]]) -> str:
    """Use the last main-agent answer block, retaining its streaming fragments."""
    final = ""
    run_id = None
    text_id = None
    for event in events:
        current_run = event.get("run_id", "trace")
        if current_run != run_id:
            final, text_id, run_id = "", None, current_run
        data = event.get("data", {})
        if not isinstance(data, dict):
            continue
        kind = event.get("event_type")
        if kind in ("run:resumed", "steer:message") or (
            data.get("depth", 0) == 0 and kind in ("agent:start", "tool:start", "tool:result")
        ):
            final, text_id = "", None
        elif kind == "message:chunk" and data.get("depth", 0) == 0:
            current_text = data.get("text_id")
            if current_text != text_id:
                final, text_id = "", current_text
            final += str(data.get("content", ""))
        elif kind in ("complete", "done"):
            # A subsequent anonymous block must not join a settled answer.
            text_id = object()
    return final


def evaluate_trace(case: dict[str, Any], trace: dict[str, Any], *, user_id: str) -> dict[str, Any]:
    if not case.get("assertions"):
        raise ValueError("case requires mechanical assertions")
    if trace.get("user_id") != user_id:
        raise ValueError("trace owner mismatch")
    if trace.get("case_id") != case["case_id"] or not trace.get("session_id"):
        raise ValueError("trace case/session mismatch")
    events = trace.get("events", [])
    if not isinstance(events, list) or any(not isinstance(event, dict) for event in events):
        raise ValueError("invalid trace events")
    for event in events:
        for scope, expected in (("session_id", trace["session_id"]), ("user_id", user_id)):
            if scope in event and event[scope] != expected:
                raise ValueError(f"event {scope} mismatch")
            data = event.get("data", {})
            if isinstance(data, dict) and scope in data and data[scope] != expected:
                raise ValueError(f"event {scope} mismatch")
    result = empty_result(case, "pass", None)
    result["elapsed_seconds"] = trace.get("elapsed_seconds")
    calls = [event for event in events if event.get("event_type") == "tool:start"]
    result["tool_calls"] = len(calls)
    effects = Counter(
        event["data"]["effect_id"]
        for event in events
        if isinstance(event.get("data"), dict) and event["data"].get("effect_id")
    )
    result["duplicate_effects"] = sum(count - 1 for count in effects.values())
    usages = {}
    run_ids = {event.get("run_id", "trace") for event in events}
    for event in events:
        if event.get("event_type") == "token:usage":
            usages[event.get("run_id", "trace")] = event.get("data", {})
    if usages and set(usages) == run_ids:
        # Usage events are cumulative snapshots per run, including resumed runs.
        for name in ("input", "output", "total"):
            values = [usage.get(f"{name}_tokens") for usage in usages.values()]
            if all(
                isinstance(value, int) and not isinstance(value, bool) and value >= 0
                for value in values
            ):
                result["tokens"][name] = sum(values)
    final = trace.get("final")
    if not isinstance(final, str):
        final = _final_answer(events)
    terminal = [
        event.get("event_type")
        for event in events
        if event.get("event_type") in ("complete", "done", "error")
    ]
    if not terminal or "error" in terminal:
        result.update(outcome="error", failure_stage="execution")
        return result
    for index, assertion in enumerate(case["assertions"]):
        kind = assertion.get("kind")
        if kind == "final_contains":
            passed = assertion["value"] in final
        elif kind == "final_not_contains":
            passed = assertion["value"] not in final
        elif kind == "event_field":
            matching = [
                event
                for event in events
                if event.get("event_type") == assertion["event_type"]
                and _field(event, assertion["field"]) == assertion["value"]
            ]
            passed = len(matching) >= assertion.get("min_count", 1)
        elif kind == "event_count":
            passed = sum(
                event.get("event_type") == assertion["event_type"] for event in events
            ) >= assertion.get("min_count", 1)
        elif kind == "tool_succeeded":
            passed = any(
                event.get("event_type") == "tool:result"
                and event.get("data", {}).get("tool") == assertion["tool"]
                and event.get("data", {}).get("success") is True
                for event in events
            )
        elif kind == "artifact_equals":
            # Compare actual observed artifact contents; never dereference an untrusted path.
            passed = any(
                event.get("event_type") == "artifact:result"
                and _field(event, assertion["field"]) == assertion["value"]
                for event in events
            )
        elif kind == "no_duplicate_effects":
            passed = result["duplicate_effects"] == 0
        else:
            raise ValueError(f"unknown mechanical assertion: {kind}")
        result["evidence"].append({"assertion_index": index, "kind": kind, "passed": passed})
        if not passed:
            result.update(outcome="fail", failure_stage="assertion")
    judge = trace.get("judge")
    if judge is not None:
        if not isinstance(judge, dict) or judge.get("outcome") not in ("pass", "fail"):
            result.update(outcome="error", failure_stage="grader")
        elif judge["outcome"] == "fail" and result["outcome"] == "pass":
            result.update(outcome="fail", failure_stage="grader")
    return result


def report_success(results: list[dict[str, Any]]) -> bool:
    return (
        bool(results)
        and any(item["outcome"] == "pass" for item in results)
        and all(item["outcome"] in ("pass", "skip") for item in results)
    )


def compare_reports(left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any]:
    if not left.get("suite_version") or left.get("suite_version") != right.get("suite_version"):
        raise ValueError("cannot compare different suite versions")
    indexed = []
    for report in (left, right):
        records = report.get("results", [])
        ids = [record["case_id"] for record in records]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate case results")
        indexed.append({record["case_id"]: record for record in records})
    if left.get("suite_sha256") != right.get("suite_sha256"):
        raise ValueError("cannot compare different suite contents")
    if left.get("mode") != right.get("mode"):
        raise ValueError("cannot compare trace diagnostics with live execution")
    if not indexed[0] or indexed[0].keys() != indexed[1].keys():
        raise ValueError("cannot compare different or empty case sets")
    return {
        "suite_version": left["suite_version"],
        "cases": [
            {
                "case_id": case_id,
                "before": indexed[0][case_id],
                "after": indexed[1][case_id],
                "changed": indexed[0][case_id]["outcome"] != indexed[1][case_id]["outcome"],
            }
            for case_id in sorted(indexed[0])
        ],
    }


def validate_live_target(url: str, *, isolated: bool) -> str:
    parsed = urlsplit(url)
    if (
        not isolated
        or parsed.scheme not in ("http", "https")
        or parsed.hostname not in ("localhost", "127.0.0.1", "::1", "test.lambchat.com")
        or parsed.username
        or parsed.password
        or parsed.path not in ("", "/")
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("live requires an explicit isolated localhost or test.lambchat.com target")
    return url.rstrip("/")


async def run_live_case(
    client: httpx.AsyncClient,
    case: dict[str, Any],
    *,
    user_id: str,
    agent_id: str,
    timeout: float,
    hooks: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Hooks perform deterministic test setup/actions when observed SSE events arrive.

    Hooks are trusted evaluator configuration, not model output. They may access only
    the freshly created session or the isolated server's explicit /__eval__/ test API.
    """
    if case.get("requires_live_hook") and not hooks:
        return empty_result(case, "skip", "fixture_setup")
    started = time.monotonic()
    session_id = None
    result = empty_result(case, "error", "execution")
    try:
        async with asyncio.timeout(timeout):
            response = await client.post("/api/sessions", json={"name": f"eval:{case['case_id']}"})
            response.raise_for_status()
            session = response.json()
            if session.get("user_id") != user_id:
                raise ValueError("session owner mismatch")
            session_id = session["id"]
            if not isinstance(session_id, str) or not session_id:
                raise ValueError("invalid session ID")
            remaining_hooks = []
            for hook in hooks or []:
                if hook["on_event"] != "session_created":
                    remaining_hooks.append(hook)
                    continue
                path = hook["path"]
                if not path.startswith("/__eval__/") or ".." in path or "?" in path:
                    raise ValueError("setup hook requires isolated fixture control")
                setup = await client.post(
                    path,
                    json={
                        **hook.get("body", {}),
                        "session_id": session_id,
                        "controlled_material": case.get("controlled_material", {}),
                    },
                )
                setup.raise_for_status()
            response = await client.post(
                "/api/chat/stream",
                params={"agent_id": agent_id},
                json={
                    **case.get("request", {}),
                    "message": case["input"],
                    "session_id": session_id,
                },
            )
            response.raise_for_status()
            run = response.json()
            if run.get("session_id") != session_id or not run.get("run_id"):
                raise ValueError("invalid submitted run scope")
            events: list[dict[str, Any]] = []
            pending = remaining_hooks
            followup_runs: list[str] = []

            async def fire_hooks(event: dict[str, Any]) -> None:
                for hook in list(pending):
                    if hook["on_event"] != event["event_type"]:
                        continue
                    path = hook["path"].replace("{session_id}", quote(session_id, safe=""))
                    for key in ("approval_id", "interrupt_id"):
                        marker = "{" + key + "}"
                        if marker in path:
                            value = event.get("data", {}).get(key) or event.get("data", {}).get(
                                "id"
                            )
                            if not isinstance(value, str):
                                raise ValueError("missing hook event ID")
                            path = path.replace(marker, quote(value, safe=""))
                    allowed = (f"/api/chat/sessions/{quote(session_id, safe='')}/", "/__eval__/")
                    approval = event.get("data", {}).get("id")
                    approval_path = (
                        f"/human/{quote(str(approval), safe='')}/respond"
                        if event["event_type"] == "approval_required" and approval
                        else None
                    )
                    if (
                        (not path.startswith(allowed) and path != approval_path)
                        or ".." in path
                        or "?" in path
                    ):
                        raise ValueError("hook path outside isolated session")
                    action = await client.post(
                        path,
                        json={
                            **hook.get("body", {}),
                            **({"session_id": session_id} if path.startswith("/__eval__/") else {}),
                        },
                    )
                    action.raise_for_status()
                    action_data = action.json()
                    next_run = action_data.get("run_id") or action_data.get("hitl_resume", {}).get(
                        "run_id"
                    )
                    if next_run and next_run != run["run_id"]:
                        followup_runs.append(next_run)
                    pending.remove(hook)

            await fire_hooks({"event_type": "submitted", "data": {}})
            followup_runs.insert(0, run["run_id"])
            while followup_runs:
                current_run = followup_runs.pop(0)
                async with client.stream(
                    "GET",
                    f"/api/chat/sessions/{quote(session_id, safe='')}/stream",
                    params={"run_id": current_run},
                ) as stream:
                    stream.raise_for_status()
                    event_type = "message"
                    data_lines: list[str] = []
                    async for line in stream.aiter_lines():
                        if line.startswith("event:"):
                            event_type = line[6:].strip()
                        elif line.startswith("data:"):
                            data_lines.append(line[5:].lstrip())
                        elif not line and data_lines:
                            data = json.loads("\n".join(data_lines))
                            if not isinstance(data, dict):
                                raise ValueError("invalid SSE data object")
                            event = {
                                "event_type": event_type,
                                "data": data,
                                "session_id": session_id,
                                "run_id": current_run,
                            }
                            events.append(event)
                            await fire_hooks(event)
                            data_lines = []
                            event_type = "message"
                            if event["event_type"] in ("complete", "done", "error"):
                                break
            result = evaluate_trace(
                case,
                {
                    "case_id": case["case_id"],
                    "user_id": user_id,
                    "session_id": session_id,
                    "events": events,
                },
                user_id=user_id,
            )
            if pending:
                result.update(outcome="error", failure_stage="fixture_hook")
    except (TimeoutError, httpx.TimeoutException):
        result.update(outcome="error", failure_stage="timeout")
    except httpx.HTTPStatusError as exc:
        result.update(
            outcome="error",
            failure_stage="authentication" if exc.response.status_code in (401, 403) else "http",
        )
    except (ValueError, KeyError, TypeError, httpx.HTTPError):
        result.update(outcome="error", failure_stage="protocol")
    finally:
        if session_id:
            try:
                async with asyncio.timeout(10):
                    cleanup = await client.delete(f"/api/sessions/{quote(session_id, safe='')}")
                    cleanup.raise_for_status()
            except (httpx.HTTPError, TimeoutError):
                result["evidence"].append({"cleanup_failed": True})
                if result["outcome"] != "error":
                    result.update(outcome="error", failure_stage="cleanup")
        result["elapsed_seconds"] = round(time.monotonic() - started, 6)
    return result
