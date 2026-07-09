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
  expect(
    reconcileSessionList({
      previous: [session("keep"), session("drop")],
      latest: [session("keep")],
      removeMissing: true,
    }).map((item) => item.id),
  ).toEqual(["keep"]);
});

test("reconcileSessionList preserves older sessions for unfiltered soft refreshes", () => {
  expect(
    reconcileSessionList({
      previous: [session("keep"), session("older-page")],
      latest: [session("new-top"), session("keep")],
      removeMissing: false,
    }).map((item) => item.id),
  ).toEqual(["new-top", "keep", "older-page"]);
});

test("reconcileSessionList does not resurrect locally deleted sessions from stale refreshes", () => {
  const input = {
    previous: [session("keep")],
    latest: [session("deleted"), session("keep")],
    removeMissing: true,
    excludedSessionIds: new Set(["deleted"]),
  };

  expect(reconcileSessionList(input).map((item) => item.id)).toEqual(["keep"]);
});
