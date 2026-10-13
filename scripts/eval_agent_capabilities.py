#!/usr/bin/env python3
"""Evaluate offline traces or explicitly configured isolated live Agent sessions.

Trace format: JSON array (or JSONL), one {case_id,user_id,session_id,events} per
case. Events use the existing {event_type,data} SSE schema. Optional final, judge,
elapsed_seconds fields are diagnostics. No trace paths/URLs are dereferenced.

Live credentials: EVAL_AGENT_TOKEN and EVAL_AGENT_USER_ID in the environment.
Advanced live lifecycle fixtures require --hooks: a versioned JSON document with
{suite_version, cases: {case_id: [{on_event,path,body}]}}. Hook paths are limited
to this newly created session and the isolated server's /__eval__/ test controls.
Unavailable fixture controls produce skip, never pass.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import sys
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.infra.agent.capability_evaluation import (  # noqa: E402
    compare_reports,
    empty_result,
    evaluate_trace,
    load_cases,
    load_traces,
    report_success,
    run_live_case,
    validate_live_target,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("trace", "live"), default="trace")
    parser.add_argument(
        "--cases", type=Path, default=ROOT / "tests/fixtures/agent_capabilities/v1.json"
    )
    parser.add_argument("--trace", type=Path)
    parser.add_argument("--user-id", help="Required expected owner of offline trace records")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--base-url", help="Explicit isolated test server; no default")
    parser.add_argument(
        "--isolated", action="store_true", help="Acknowledge server is isolated for this evaluation"
    )
    parser.add_argument("--agent-id", default="fast")
    parser.add_argument("--timeout", type=float, default=120)
    parser.add_argument("--hooks", type=Path)
    parser.add_argument("--compare", nargs=2, type=Path, metavar=("BEFORE", "AFTER"))
    args = parser.parse_args()
    try:
        if args.compare:
            report = compare_reports(*(json.loads(path.read_text()) for path in args.compare))
            args.output.write_text(json.dumps(report, indent=2) + "\n")
            return 0
        suite = load_cases(args.cases)
        if args.timeout <= 0:
            raise ValueError("timeout must be positive")
        if args.mode == "trace":
            if not args.trace or not args.user_id:
                raise ValueError("trace mode requires --trace and --user-id")
            traces = load_traces(args.trace)
            if set(traces) - {case["case_id"] for case in suite["cases"]}:
                raise ValueError("trace contains unknown cases")
            results = []
            for case in suite["cases"]:
                trace = traces.get(case["case_id"])
                if trace and trace.get("suite_version", suite["version"]) != suite["version"]:
                    raise ValueError("trace suite version mismatch")
                results.append(
                    evaluate_trace(case, trace, user_id=args.user_id)
                    if trace
                    else empty_result(case, "skip", "missing_trace")
                )
        else:
            if not args.base_url:
                raise ValueError("live mode requires --base-url")
            base_url = validate_live_target(args.base_url, isolated=args.isolated)
            token = os.environ.get("EVAL_AGENT_TOKEN")
            user_id = os.environ.get("EVAL_AGENT_USER_ID")
            if not token or not user_id:
                raise ValueError("live requires EVAL_AGENT_TOKEN and EVAL_AGENT_USER_ID")
            hooks = (
                json.loads(args.hooks.read_text())
                if args.hooks
                else {"suite_version": suite["version"], "cases": {}}
            )
            if hooks.get("suite_version") != suite["version"]:
                raise ValueError("hook suite version mismatch")

            async def live():
                async with httpx.AsyncClient(
                    base_url=base_url,
                    headers={"Authorization": f"Bearer {token}"},
                    timeout=args.timeout,
                    follow_redirects=False,
                ) as client:
                    return [
                        await run_live_case(
                            client,
                            case,
                            user_id=user_id,
                            agent_id=args.agent_id,
                            timeout=args.timeout,
                            hooks=hooks["cases"].get(case["case_id"]),
                        )
                        for case in suite["cases"]
                    ]

            results = asyncio.run(live())
        report = {
            "schema_version": 1,
            "suite_version": suite["version"],
            "suite_sha256": hashlib.sha256(json.dumps(suite, sort_keys=True).encode()).hexdigest(),
            "mode": args.mode,
            "agent_id": args.agent_id if args.mode == "live" else None,
            "agent_reexecuted": args.mode == "live",
            "results": results,
            "counts": {
                outcome: sum(result["outcome"] == outcome for result in results)
                for outcome in ("pass", "fail", "error", "skip")
            },
            "success": report_success(results),
        }
        args.output.write_text(json.dumps(report, indent=2) + "\n")
        return 0 if report["success"] else 1
    except (ValueError, KeyError, TypeError, OSError) as exc:
        # Error messages come from local schema validation, never HTTP response bodies.
        print(f"evaluation configuration error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
