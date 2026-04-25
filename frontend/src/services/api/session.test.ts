import test from "node:test";
import assert from "node:assert/strict";
import { buildSessionRunsUrl } from "./session.ts";

test("builds the default session runs url", () => {
  assert.equal(
    buildSessionRunsUrl("session-1"),
    "/api/sessions/session-1/runs",
  );
});

test("includes trace_id when looking up a specific run by trace", () => {
  assert.equal(
    buildSessionRunsUrl("session-1", { trace_id: "trace-123" }),
    "/api/sessions/session-1/runs?trace_id=trace-123",
  );
});
