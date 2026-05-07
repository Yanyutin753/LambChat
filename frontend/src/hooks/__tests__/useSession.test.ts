import test from "node:test";
import assert from "node:assert/strict";

import type { BackendSession } from "../../services/api/session.ts";
import { reconcileSessionList } from "../useSession.ts";

function session(id: string): BackendSession {
  return {
    id,
    agent_id: "default",
    created_at: "2026-04-26T00:00:00.000Z",
    updated_at: "2026-04-26T00:00:00.000Z",
    is_active: true,
    metadata: {},
  };
}

test("reconcileSessionList removes sessions missing from a filtered refresh", () => {
  assert.deepEqual(
    reconcileSessionList({
      previous: [session("keep"), session("drop")],
      latest: [session("keep")],
      removeMissing: true,
    }).map((item) => item.id),
    ["keep"],
  );
});

test("reconcileSessionList preserves older sessions for unfiltered soft refreshes", () => {
  assert.deepEqual(
    reconcileSessionList({
      previous: [session("keep"), session("older-page")],
      latest: [session("new-top"), session("keep")],
      removeMissing: false,
    }).map((item) => item.id),
    ["new-top", "keep", "older-page"],
  );
});
