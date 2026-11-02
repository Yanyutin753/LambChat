import { beforeEach, describe, expect, test, vi } from "vitest";
import {
  groupPendingHydrations,
  hydrateScheduledEvents,
  resetScheduledHydrationCache,
} from "../scheduledEventHydration";
import type { Message } from "../../../types";

beforeEach(() => {
  resetScheduledHydrationCache();
});

function scheduledMessage(
  id: string,
  overrides: Partial<Message["metadata"]> = {},
): Message {
  return {
    id,
    role: "assistant",
    content: "done",
    timestamp: new Date("2026-10-16T17:46:50Z"),
    runId: id.replace("scheduled-result:", ""),
    metadata: {
      scheduledTaskId: "task",
      scheduledTaskName: "Numbers",
      scheduledFinal: true,
      scheduledExecutionSessionId: "sch_conversation_task",
      scheduledEventsLoaded: false,
      ...overrides,
    },
  };
}

describe("groupPendingHydrations", () => {
  test("collects only final cards without loaded events, grouped by execution session", () => {
    const groups = groupPendingHydrations([
      scheduledMessage("scheduled-result:run-1"),
      scheduledMessage("scheduled-result:run-2"),
      scheduledMessage("scheduled-result:run-3", {
        scheduledExecutionSessionId: "sch_other",
      }),
      scheduledMessage("scheduled-result:run-4", {
        scheduledEventsLoaded: true,
      }),
      scheduledMessage("scheduled-result:run-5", { scheduledFinal: false }),
      { id: "human", role: "assistant", content: "hi", timestamp: new Date() },
    ]);
    expect(groups).toEqual([
      {
        executionSessionId: "sch_conversation_task",
        runIds: ["run-1", "run-2"],
      },
      { executionSessionId: "sch_other", runIds: ["run-3"] },
    ]);
  });

  test("messages without a run id or task metadata are ignored", () => {
    const noRun: Message = {
      ...scheduledMessage("scheduled-result:x"),
      runId: undefined,
    };
    expect(groupPendingHydrations([noRun])).toEqual([]);
    expect(
      groupPendingHydrations([
        scheduledMessage("scheduled-result:x", {
          scheduledTaskId: undefined,
          scheduledTaskName: "Numbers",
        }),
      ]),
    ).toEqual([]);
  });
});

type Fetcher = ReturnType<typeof vi.fn>;

function eventFor(runId: string) {
  return { event_type: "done", data: {}, run_id: runId };
}

describe("hydrateScheduledEvents", () => {
  test("fetches once per source and serves repeats from the module cache", async () => {
    const fetcher: Fetcher = vi.fn(async (_source: string, runIds: string[]) =>
      runIds.map((runId) => eventFor(runId)),
    );
    const first = await hydrateScheduledEvents(
      [
        { executionSessionId: "sch_a", runIds: ["r1", "r2"] },
        { executionSessionId: "sch_b", runIds: ["r3"] },
      ],
      fetcher,
    );
    expect(fetcher).toHaveBeenCalledTimes(2);
    expect(fetcher).toHaveBeenNthCalledWith(1, "sch_a", ["r1", "r2"]);
    expect(first.get("r1")).toEqual([eventFor("r1")]);
    expect(first.get("r3")).toEqual([eventFor("r3")]);

    const second = await hydrateScheduledEvents(
      [{ executionSessionId: "sch_a", runIds: ["r1", "r2"] }],
      fetcher,
    );
    expect(fetcher).toHaveBeenCalledTimes(2);
    expect(second.get("r2")).toEqual([eventFor("r2")]);
  });

  test("only uncached run ids hit the network", async () => {
    const fetcher: Fetcher = vi.fn(async (_source: string, runIds: string[]) =>
      runIds.map((runId) => eventFor(runId)),
    );
    await hydrateScheduledEvents(
      [{ executionSessionId: "sch_a", runIds: ["r1"] }],
      fetcher,
    );
    await hydrateScheduledEvents(
      [{ executionSessionId: "sch_a", runIds: ["r1", "r2"] }],
      fetcher,
    );
    expect(fetcher).toHaveBeenCalledTimes(2);
    expect(fetcher).toHaveBeenLastCalledWith("sch_a", ["r2"]);
  });

  test("concurrent identical requests share one in-flight call", async () => {
    let release: (() => void) | undefined;
    const fetcher: Fetcher = vi.fn(
      (_source: string, runIds: string[]) =>
        new Promise((resolve) => {
          release = () => resolve(runIds.map((runId) => eventFor(runId)));
        }),
    );
    const p1 = hydrateScheduledEvents(
      [{ executionSessionId: "sch_a", runIds: ["r1"] }],
      fetcher,
    );
    const p2 = hydrateScheduledEvents(
      [{ executionSessionId: "sch_a", runIds: ["r1"] }],
      fetcher,
    );
    release?.();
    const [a, b] = await Promise.all([p1, p2]);
    expect(fetcher).toHaveBeenCalledTimes(1);
    expect(a.get("r1")).toEqual([eventFor("r1")]);
    expect(b.get("r1")).toEqual([eventFor("r1")]);
  });

  test("batches larger than the chunk size split into several fetches", async () => {
    const fetcher: Fetcher = vi.fn(async (_source: string, runIds: string[]) =>
      runIds.map((runId) => eventFor(runId)),
    );
    const runIds = Array.from({ length: 120 }, (_, i) => `r${i}`);
    const result = await hydrateScheduledEvents(
      [{ executionSessionId: "sch_a", runIds }],
      fetcher,
    );
    expect(fetcher).toHaveBeenCalledTimes(3);
    expect(result.size).toBe(120);
    expect(result.get("r119")).toEqual([eventFor("r119")]);
  });

  test("fetch failures leave the cache empty so the next pass retries", async () => {
    const fetcher: Fetcher = vi.fn().mockRejectedValue(new Error("offline"));
    const result = await hydrateScheduledEvents(
      [{ executionSessionId: "sch_a", runIds: ["r1"] }],
      fetcher,
    );
    expect(result.size).toBe(0);
    const retry: Fetcher = vi.fn(async (_source: string, runIds: string[]) =>
      runIds.map((runId) => eventFor(runId)),
    );
    const second = await hydrateScheduledEvents(
      [{ executionSessionId: "sch_a", runIds: ["r1"] }],
      retry,
    );
    expect(second.get("r1")).toEqual([eventFor("r1")]);
  });
});
