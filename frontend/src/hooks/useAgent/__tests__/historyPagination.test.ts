import { describe, expect, test } from "vitest";
import {
  HISTORY_TRACE_PAGE_SIZE,
  resolveHistoryTraceWindow,
  canLoadOlderHistory,
  mergeOlderHistoryEvents,
} from "../historyPagination";
import type { HistoryEvent } from "../types";

function event(runId: string, content: string): HistoryEvent {
  return {
    id: `${runId}-${content}`,
    event_type: "message:chunk",
    data: { content },
    run_id: runId,
    timestamp: `2026-08-01T00:00:0${content.length % 10}Z`,
  };
}

describe("resolveHistoryTraceWindow", () => {
  test("keeps the cursor and continues paging when more traces exist", () => {
    expect(
      resolveHistoryTraceWindow({
        has_more_traces: true,
        trace_window: {
          oldest_trace_started_at: "2026-08-01T00:10:00Z",
          oldest_trace_id: "trace-4",
        },
      }),
    ).toEqual({
      traceWindow: {
        oldest_trace_started_at: "2026-08-01T00:10:00Z",
        oldest_trace_id: "trace-4",
      },
      hasMore: true,
    });
  });

  test("stops paging when the backend says no more traces", () => {
    expect(
      resolveHistoryTraceWindow({
        has_more_traces: false,
        trace_window: {
          oldest_trace_started_at: "2026-08-01T00:01:00Z",
          oldest_trace_id: "trace-1",
        },
      }),
    ).toEqual({
      traceWindow: {
        oldest_trace_started_at: "2026-08-01T00:01:00Z",
        oldest_trace_id: "trace-1",
      },
      hasMore: false,
    });
  });

  test("stops paging when no cursor is returned even if more is claimed", () => {
    expect(resolveHistoryTraceWindow({ has_more_traces: true })).toEqual({
      traceWindow: null,
      hasMore: false,
    });
    expect(resolveHistoryTraceWindow({})).toEqual({
      traceWindow: null,
      hasMore: false,
    });
  });
});

describe("canLoadOlderHistory", () => {
  const base = {
    sessionId: "session-1",
    traceWindow: {
      oldest_trace_started_at: "2026-08-01T00:10:00Z",
      oldest_trace_id: "trace-4",
    },
    hasMore: true,
    isLoading: false,
  };

  test("allows paging with a session, cursor, more pages and idle state", () => {
    expect(canLoadOlderHistory(base)).toBe(true);
  });

  test("blocks paging without a session or cursor", () => {
    expect(canLoadOlderHistory({ ...base, sessionId: null })).toBe(false);
    expect(canLoadOlderHistory({ ...base, traceWindow: null })).toBe(false);
  });

  test("blocks paging when exhausted or already loading", () => {
    expect(canLoadOlderHistory({ ...base, hasMore: false })).toBe(false);
    expect(canLoadOlderHistory({ ...base, isLoading: true })).toBe(false);
  });
});

describe("mergeOlderHistoryEvents", () => {
  test("prepends the older page before the already loaded events", () => {
    const current = [event("run-3", "latest")];
    const older = [event("run-1", "oldest"), event("run-2", "older")];

    expect(mergeOlderHistoryEvents(older, current)).toEqual([
      ...older,
      ...current,
    ]);
  });

  test("keeps current events untouched when the older page is empty", () => {
    const current = [event("run-3", "latest")];
    expect(mergeOlderHistoryEvents([], current)).toEqual(current);
  });
});

test("history page size stays within the backend trace window cap", () => {
  expect(HISTORY_TRACE_PAGE_SIZE).toBeGreaterThan(0);
  expect(HISTORY_TRACE_PAGE_SIZE).toBeLessThanOrEqual(200);
});
