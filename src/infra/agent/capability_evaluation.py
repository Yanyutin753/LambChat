"""Offline diagnostics and explicitly isolated live Agent evaluation.

Trace documents are supplied by the caller, never resolved through paths/URLs in a
trace. Mechanical assertions inspect recorded events, not a model's claim of success.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import re
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


def _completed_summary_count(events: list[dict[str, Any]]) -> int:
    """Count successful compression stats by their original Redis stream identity."""
    completed = set()
    for event in events:
        data = event.get("data")
        if event.get("event_type") != "summary" or not isinstance(data, dict):
            continue
        freed = data.get("freed_tokens")
        if data.get("depth", 0) != 0 or type(freed) is not int or freed <= 0:
            continue
        run_id, event_id = event.get("run_id"), event.get("id")
        if not isinstance(run_id, str) or not run_id.strip() or not isinstance(event_id, str):
            continue
        if not re.fullmatch(r"(?:0|[1-9][0-9]{0,19})-(?:0|[1-9][0-9]{0,19})", event_id):
            continue
        if event_id == "0-0" or any(int(part) > 2**64 - 1 for part in event_id.split("-")):
            continue
        completed.add((run_id, event_id))
    return len(completed)


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


def _fixture_witnesses(trace: dict[str, Any], user_id: str) -> list[dict[str, Any]]:
    """Validate explicitly supplied fixture observations, never model claims."""
    witnesses = trace.get("fixture_evidence", [])
    if not isinstance(witnesses, list):
        raise ValueError("invalid fixture witness list")
    artifacts = set()
    for event in trace.get("events", []):
        data = event.get("data")
        if not isinstance(data, dict):
            continue
        if event.get("event_type") == "artifact:result" and data.get("success") is not False:
            artifact = data.get("artifact")
            if isinstance(artifact, dict):
                artifacts.add((artifact.get("id"), artifact.get("path")))
        elif (
            event.get("event_type") == "tool:result"
            and data.get("tool") == "reveal_file"
            and data.get("success") is True
        ):
            identity = _field(data, "result.key")
            path = _field(data, "result._meta.path")
            if isinstance(identity, str) and isinstance(path, str):
                artifacts.add((identity, path))
    for witness in witnesses:
        if (
            not isinstance(witness, dict)
            or witness.get("user_id") != user_id
            or witness.get("session_id") != trace["session_id"]
        ):
            raise ValueError("fixture witness scope mismatch")
        if witness.get("kind") == "artifact_readback":
            content = witness.get("content")
            if (
                not isinstance(content, str)
                or not isinstance(witness.get("artifact_id"), str)
                or not witness["artifact_id"]
                or not isinstance(witness.get("path"), str)
                or not witness["path"]
                or (witness.get("artifact_id"), witness.get("path")) not in artifacts
                or witness.get("content_sha256") != hashlib.sha256(content.encode()).hexdigest()
            ):
                raise ValueError("artifact witness identity/content mismatch")
        elif witness.get("kind") == "effect_counts":
            effects = witness.get("effects")
            if not isinstance(effects, list) or not effects:
                raise ValueError("missing effect witness counts")
            seen = set()
            for effect in effects:
                if not isinstance(effect, dict):
                    raise ValueError("invalid effect witness")
                identity = effect.get("effect_id")
                attempts, committed = effect.get("attempt_count"), effect.get("committed_count")
                if (
                    not isinstance(identity, str)
                    or not identity
                    or identity in seen
                    or type(attempts) is not int
                    or type(committed) is not int
                    or not 0 <= committed <= attempts
                ):
                    raise ValueError("invalid effect witness counts")
                seen.add(identity)
        else:
            raise ValueError("unknown fixture witness kind")
    return witnesses


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
    witnesses = _fixture_witnesses(trace, user_id)
    effect_witnesses = [item for item in witnesses if item["kind"] == "effect_counts"]
    effect_counts: dict[str, int] = {}
    if effect_witnesses:
        # Multiple cumulative observations must not count the same commit twice.
        for witness in effect_witnesses:
            for effect in witness["effects"]:
                identity = effect["effect_id"]
                effect_counts[identity] = max(
                    effect_counts.get(identity, 0), effect["committed_count"]
                )
        result["duplicate_effects"] = sum(max(count - 1, 0) for count in effect_counts.values())
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
        elif kind == "summary_count":
            passed = _completed_summary_count(events) >= assertion.get("min_count", 1)
        elif kind == "tool_succeeded":
            passed = any(
                event.get("event_type") == "tool:result"
                and event.get("data", {}).get("tool") == assertion["tool"]
                and event.get("data", {}).get("success") is True
                and _field(event, "data.result.success") is not False
                for event in events
            )
        elif kind == "artifact_equals":
            readbacks = [item for item in witnesses if item["kind"] == "artifact_readback"]
            if not readbacks:
                result.update(outcome="error", failure_stage="fixture_evidence")
                return result
            passed = any(
                _field({"data": {"content": item["content"]}}, assertion["field"])
                == assertion["value"]
                for item in readbacks
            )
        elif kind == "no_duplicate_effects":
            if not effect_witnesses and result["duplicate_effects"] == 0:
                result.update(outcome="error", failure_stage="fixture_evidence")
                return result
            expected = assertion.get("effect_id") or case.get("controlled_material", {}).get(
                "effect_id"
            )
            passed = (
                bool(effect_witnesses)
                and result["duplicate_effects"] == 0
                and (
                    effect_counts.get(expected) == 1
                    if expected
                    else all(count == 1 for count in effect_counts.values())
                )
            )
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
            fixture_evidence: list[dict[str, Any]] = []
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
                    params = hook.get("params")
                    if params is not None and (
                        path != approval_path
                        or not isinstance(params, dict)
                        or set(params) - {"approved", "response"}
                        or type(params.get("approved")) is not bool
                        or not isinstance(params.get("response", "{}"), str)
                    ):
                        raise ValueError("unsupported approval hook parameters")
                    collect = hook.get("collect")
                    if collect and (
                        not path.startswith("/__eval__/")
                        or collect not in {"effect_counts", "artifact_readback"}
                    ):
                        raise ValueError("unsupported fixture witness collector")
                    action = await client.post(
                        path,
                        params=params,
                        json={
                            **hook.get("body", {}),
                            **({"session_id": session_id} if path.startswith("/__eval__/") else {}),
                            **({"observed_event": event} if collect else {}),
                        },
                    )
                    action.raise_for_status()
                    action_data = action.json()
                    if collect:
                        witness = action_data.get("witness")
                        if not isinstance(witness, dict) or witness.get("kind") != collect:
                            raise ValueError("missing fixture witness")
                        fixture_evidence.append(witness)
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
                    event_id = None
                    data_lines: list[str] = []
                    async for line in stream.aiter_lines():
                        if line.startswith("event:"):
                            event_type = line[6:].strip()
                        elif line.startswith("data:"):
                            data_lines.append(line[5:].lstrip())
                        elif line.startswith("id:"):
                            event_id = line[3:].removeprefix(" ")
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
                            if event_id is not None:
                                event["id"] = event_id
                            events.append(event)
                            await fire_hooks(event)
                            data_lines = []
                            event_type = "message"
                            event_id = None
                            if event["event_type"] in ("complete", "done", "error"):
                                break
                        elif not line:
                            event_type = "message"
                            event_id = None
            result = evaluate_trace(
                case,
                {
                    "case_id": case["case_id"],
                    "user_id": user_id,
                    "session_id": session_id,
                    "events": events,
                    "fixture_evidence": fixture_evidence,
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
