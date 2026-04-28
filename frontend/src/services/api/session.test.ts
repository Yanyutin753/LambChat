import test from "node:test";
import assert from "node:assert/strict";
import { buildSessionRunsUrl, buildSubmitChatBody } from "./session.ts";

test("builds a session list url with favorites_only", () => {
  const searchParams = new URLSearchParams();
  searchParams.set("favorites_only", "true");
  assert.equal(
    `/api/sessions?${searchParams.toString()}`,
    "/api/sessions?favorites_only=true",
  );
});

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

test("includes user_timezone in the submit chat body when available", () => {
  assert.deepEqual(
    buildSubmitChatBody({
      message: "hello",
      sessionId: "session-1",
      userTimezone: "Asia/Shanghai",
    }),
    {
      message: "hello",
      session_id: "session-1",
      agent_options: undefined,
      attachments: undefined,
      disabled_skills: undefined,
      disabled_mcp_tools: undefined,
      user_timezone: "Asia/Shanghai",
    },
  );
});
