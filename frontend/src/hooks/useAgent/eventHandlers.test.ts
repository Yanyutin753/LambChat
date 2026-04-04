import test from "node:test";
import assert from "node:assert/strict";
import { shouldAcceptMetadataSessionId } from "./eventHandlers.ts";

test("accepts metadata session id when there is no current session and it matches the active stream", () => {
  assert.equal(
    shouldAcceptMetadataSessionId(null, "session-new", "session-new"),
    true,
  );
});

test("rejects metadata session id from a stale stream after the user cleared the current session", () => {
  assert.equal(
    shouldAcceptMetadataSessionId(null, "session-old", "session-new"),
    false,
  );
});

test("rejects metadata session id once a current session is already selected", () => {
  assert.equal(
    shouldAcceptMetadataSessionId("session-current", "session-old", "session-old"),
    false,
  );
});
