# Agent capability suite version 2

Nine versioned cases describe controlled input/material and mechanical assertions.
An offline trace is supplied explicitly; it is diagnostic evidence, not an Agent
execution. Each JSON/JSONL record contains `case_id`, expected `user_id`, one
`session_id`, and `events` using the existing SSE `{event_type,data}` schema.
The fixture remains at `v1.json` for existing CLI paths; its version is now `2`
because compression requires completed summaries instead of streaming frame counts.
The `summary_count` assertion counts only main-agent successful-compression stats
with a positive integer `data.freed_tokens`. Each must retain its original Redis
SSE `id` and nonempty `run_id`; repeated `(run_id, id)` pairs count once. Streaming
chunks, child-agent stats, zero/invalid release counts, and events lacking these
durable IDs do not count. Live collection preserves existing SSE IDs. Do not
invent IDs from timestamps, array positions, or legacy trace normalization.
Generic `event_count` still counts individual frames.
Optional `final`, `elapsed_seconds`, and `judge: {outcome: pass|fail}` are supported.
When `final` is absent, final-answer assertions use the last main-agent text block
in the last controlled run. Fragments sharing its `text_id` are joined; tool,
steering and resumed-run boundaries discard prior drafts. Event and usage
assertions still cover all controlled runs. Unknown usage remains null. A model grader can reject, but cannot override a
failed mechanical assertion. No filesystem path or URL from a trace is read.

```sh
python3 scripts/run_validation.py uv run python scripts/eval_agent_capabilities.py \
  --mode trace --trace /tmp/agent-traces.jsonl --user-id isolated-user \
  --output /tmp/agent-results.json

# Set EVAL_AGENT_TOKEN and EVAL_AGENT_USER_ID in your shell; never put secrets in a fixture.
python3 scripts/run_validation.py uv run python scripts/eval_agent_capabilities.py \
  --mode live --base-url http://127.0.0.1:8021 --isolated \
  --hooks /tmp/isolated-hooks.json --output /tmp/agent-live-results.json

python3 scripts/run_validation.py uv run python scripts/eval_agent_capabilities.py \
  --compare /tmp/baseline.json /tmp/candidate.json --output /tmp/comparison.json
```

Live creates fresh authenticated sessions, submits through `/api/chat/stream`,
reads run-scoped SSE, and deletes only those sessions. URLs are restricted to
localhost or the explicit staging hostname `test.lambchat.com`; redirects are
not followed. An isolated test user and model/tool setup are required.

Eight lifecycle/tool cases require preprovisioned fixture controls. Without hooks
they produce `skip/fixture_setup`; prompt text alone cannot prove a restart,
approval, compression, or actual artifact contents. The isolated server must
supply the controlled materials and expose any required `/__eval__/` test controls.
This suite does not install those controls into production. The insufficient
proof case can run without instrumentation.

Hook file shape:

```json
{
  "suite_version": "2",
  "cases": {
    "steer_constraints": [
      {"on_event":"session_created","path":"/__eval__/setup","body":{"case_id":"steer_constraints"}},
      {"on_event":"tool:start","path":"/api/chat/sessions/{session_id}/steer","body":{"message":"Return only blue."}}
    ],
    "approval_resume": [
      {"on_event":"approval_required","path":"/human/{approval_id}/respond","body":{"approved":true,"values":{}}}
    ]
  }
}
```

Hooks fire once on observed events, support session and approval ID substitution,
and cannot target another session or an arbitrary URL. Approval responses may
start a new run; the runner follows `hitl_resume.run_id` and counts its usage.
Test controls should scope their mutations by the injected `session_id` and
produce auditable real events. Unfired hooks, malformed responses, auth failure,
timeout, cleanup failure, and absent terminal events never pass. `session_created` hooks install controlled material before model submission.
Configure long controlled tools so the steering hook arrives during execution.

Results contain assertion indices and booleans, metrics, and stable failure stages;
they omit raw prompts, tool outputs, session identities, and credentials. An empty
suite or an all-skip run exits nonzero. A/B comparison rejects case/version/content
mismatches and rejects mixing live execution with trace diagnostics.


## Isolated fixture host requirements

The hook sample above is a configuration contract; no fixture host is currently
shipped. Pointing it at an ordinary LambChat server will fail setup. A genuine
nine-case live run needs a standalone test harness with the following setup:

1. Boot the real API and worker using dedicated test database/Redis namespaces,
   an isolated user and a real configured model. Bind fixture controls to loopback
   in the harness-created app only; do not register `/__eval__/` in `src/api/main.py`.
2. Serve source-a/source-b and primary/fallback from a local controlled HTTP/MCP
   source, and use a temporary sandbox directory. Install per-session fixtures
   before submission through the `session_created` setup hook.
3. Have the setup control select fixtures for steering, two actual context
   summaries, child messaging, approval-gated writes, worker restart, source
   failure, and artifact readback. Exercise production API/SSE/tool handlers;
   do not inject success events or replace model answers with canned responses.
4. For recovery, terminate and restart only the worker process owned by this
   harness after the observed `tool:start`. Preserve that test worker's checkpoint
   and queue storage. Record write effects in an independent fixture ledger to
   verify the same operation was not repeated.
5. Read the actual artifact bytes from the temporary directory for the observed
   `artifact:result`, and remove all harness processes, users, namespaces and
   temporary files on exit. Never point restart hooks at a shared staging worker.

Run the locked live command above only after this host reports its fixtures ready.
Keep skipped cases visible in results until their fixture controls are implemented;
protocol tests using MockTransport and offline traces do not establish these live
capabilities.
