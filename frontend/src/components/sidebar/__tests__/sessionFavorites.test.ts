import assert from "node:assert/strict";
import test from "node:test";

import type { BackendSession } from "../../../services/api/session.ts";
import { isSessionFavorite } from "../sessionFavorites.ts";

function session(metadata: Record<string, unknown>): BackendSession {
  return {
    id: "session-1",
    agent_id: "default",
    created_at: "2026-04-26T00:00:00.000Z",
    updated_at: "2026-04-26T00:00:00.000Z",
    is_active: true,
    metadata,
  };
}

test("reads favorite state from normalized session metadata", () => {
  assert.equal(isSessionFavorite(session({ is_favorite: true })), true);
  assert.equal(isSessionFavorite(session({ is_favorite: false })), false);
});
