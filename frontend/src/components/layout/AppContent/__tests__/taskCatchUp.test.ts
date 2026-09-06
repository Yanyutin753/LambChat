import {
  selectCatchUpCandidates,
  type CatchUpSessionSnapshot,
} from "../taskCatchUp";

const HIDDEN_AT = Date.parse("2026-09-06T10:00:00.000Z");
const COMPLETED_WHILE_HIDDEN = "2026-09-06T10:05:00.000Z";
const COMPLETED_LONG_BEFORE = "2026-09-06T09:00:00.000Z";

function snapshot(
  overrides: Partial<CatchUpSessionSnapshot>,
): CatchUpSessionSnapshot {
  return {
    id: "s1",
    task_status: "completed",
    updated_at: COMPLETED_WHILE_HIDDEN,
    name: "Session One",
    unread_count: 1,
    metadata: {},
    ...overrides,
  };
}

test("selects sessions that finished while the app was hidden", () => {
  const candidates = selectCatchUpCandidates({
    sessions: [snapshot({ id: "s1" })],
    hiddenAt: HIDDEN_AT,
    currentSessionId: "other",
    hasNotified: () => false,
  });

  expect(candidates).toHaveLength(1);
  expect(candidates[0]).toMatchObject({
    session_id: "s1",
    status: "completed",
  });
});

test("skips sessions whose last update predates going hidden", () => {
  const candidates = selectCatchUpCandidates({
    sessions: [snapshot({ id: "stale", updated_at: COMPLETED_LONG_BEFORE })],
    hiddenAt: HIDDEN_AT,
    currentSessionId: "other",
    hasNotified: () => false,
  });

  expect(candidates).toHaveLength(0);
});

test("tolerates minor client clock skew around the hidden timestamp", () => {
  // 设备时钟略慢于服务器：完成时间略早于本地记录的 hiddenAt，仍应通知
  const slightlyEarly = new Date(HIDDEN_AT - 60_000).toISOString();
  const candidates = selectCatchUpCandidates({
    sessions: [snapshot({ id: "skew", updated_at: slightlyEarly })],
    hiddenAt: HIDDEN_AT,
    currentSessionId: "other",
    hasNotified: () => false,
  });

  expect(candidates).toHaveLength(1);
});

test("skips the session the user is currently viewing", () => {
  const candidates = selectCatchUpCandidates({
    sessions: [snapshot({ id: "current" })],
    hiddenAt: HIDDEN_AT,
    currentSessionId: "current",
    hasNotified: () => false,
  });

  expect(candidates).toHaveLength(0);
});

test("skips runs already notified through live websocket delivery", () => {
  const candidates = selectCatchUpCandidates({
    sessions: [snapshot({ id: "s1", metadata: { current_run_id: "run-1" } })],
    hiddenAt: HIDDEN_AT,
    currentSessionId: "other",
    hasNotified: (key) => key === "task:run-1:completed",
  });

  expect(candidates).toHaveLength(0);
});

test("skips running sessions and statuses that do not warrant a notification", () => {
  const candidates = selectCatchUpCandidates({
    sessions: [
      snapshot({ id: "running", task_status: "running" }),
      snapshot({ id: "queued", task_status: "queued" }),
      snapshot({ id: "cancelled", task_status: "cancelled" }),
      snapshot({ id: "idle", task_status: null }),
    ],
    hiddenAt: HIDDEN_AT,
    currentSessionId: "other",
    hasNotified: () => false,
  });

  expect(candidates).toHaveLength(0);
});

test("notifies failed and waiting-human completions too", () => {
  const candidates = selectCatchUpCandidates({
    sessions: [
      snapshot({ id: "failed", task_status: "failed" }),
      snapshot({ id: "waiting", task_status: "waiting_human" }),
    ],
    hiddenAt: HIDDEN_AT,
    currentSessionId: "other",
    hasNotified: () => false,
  });

  expect(candidates.map((c) => c.status).sort()).toEqual([
    "failed",
    "waiting_human",
  ]);
});

test("derives the websocket dedupe key from the run id when present", () => {
  const [candidate] = selectCatchUpCandidates({
    sessions: [snapshot({ id: "s1", metadata: { current_run_id: "run-9" } })],
    hiddenAt: HIDDEN_AT,
    currentSessionId: "other",
    hasNotified: () => false,
  });

  expect(candidate?.dedupeKey).toBe("task:run-9:completed");
});

test("falls back to a session-scoped dedupe key when run id is missing", () => {
  const [candidate] = selectCatchUpCandidates({
    sessions: [snapshot({ id: "s1", metadata: {} })],
    hiddenAt: HIDDEN_AT,
    currentSessionId: "other",
    hasNotified: () => false,
  });

  expect(candidate?.dedupeKey).toBe(
    `task:catchup:s1:${COMPLETED_WHILE_HIDDEN}:completed`,
  );
});

test("caps the number of catch-up notifications to avoid spam", () => {
  const sessions = Array.from({ length: 8 }, (_, i) =>
    snapshot({ id: `s${i}` }),
  );
  const candidates = selectCatchUpCandidates({
    sessions,
    hiddenAt: HIDDEN_AT,
    currentSessionId: "other",
    hasNotified: () => false,
  });

  expect(candidates.length).toBeLessThanOrEqual(5);
});
