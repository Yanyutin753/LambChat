import { describe, expect, test, vi } from "vitest";

import {
  resolveQueuePollAction,
  startQueuePositionPolling,
} from "../queuePolling";

describe("resolveQueuePollAction", () => {
  test("queued run keeps polling and returns live position", () => {
    expect(
      resolveQueuePollAction(
        { run_id: "run-1", task_status: "queued", position: 3 },
        "run-1",
      ),
    ).toBe(3);
  });

  test("pending run is treated as queue-side state", () => {
    expect(
      resolveQueuePollAction(
        { run_id: "run-1", task_status: "pending", position: 1 },
        "run-1",
      ),
    ).toBe(1);
  });

  test("run id change stops polling (new turn took over)", () => {
    expect(
      resolveQueuePollAction(
        { run_id: "run-2", task_status: "queued", position: 2 },
        "run-1",
      ),
    ).toBeNull();
  });

  test("processing/terminal states stop polling", () => {
    for (const task_status of ["running", "completed", "failed", "cancelled"]) {
      expect(
        resolveQueuePollAction(
          { run_id: "run-1", task_status, position: 0 },
          "run-1",
        ),
      ).toBeNull();
    }
  });
});

describe("startQueuePositionPolling", () => {
  test("updates toast with fresh positions until run leaves queue", async () => {
    vi.useFakeTimers();
    const snapshots = [
      { run_id: "run-1", task_status: "queued", position: 3 },
      { run_id: "run-1", task_status: "queued", position: 2 },
      { run_id: "run-1", task_status: "running", position: 0 },
      { run_id: "run-1", task_status: "queued", position: 9 }, // 不应再被消费
    ];
    const updates: number[] = [];
    const fetchSnapshot = vi.fn(async () => snapshots.shift());
    const onUpdate = vi.fn((position: number) => updates.push(position));

    startQueuePositionPolling(
      "session-1",
      "run-1",
      fetchSnapshot,
      onUpdate,
      10,
    );

    await vi.advanceTimersByTimeAsync(10);
    await vi.advanceTimersByTimeAsync(10);
    await vi.advanceTimersByTimeAsync(10);

    expect(updates).toEqual([3, 2]);
    expect(fetchSnapshot).toHaveBeenCalledTimes(3);
    vi.useRealTimers();
  });

  test("stops on fetch error without throwing", async () => {
    vi.useFakeTimers();
    const onUpdate = vi.fn();
    const fetchSnapshot = vi.fn(async () => {
      throw new Error("network down");
    });

    startQueuePositionPolling(
      "session-1",
      "run-1",
      fetchSnapshot,
      onUpdate,
      10,
    );

    await vi.advanceTimersByTimeAsync(50);
    expect(fetchSnapshot).toHaveBeenCalledTimes(1);
    expect(onUpdate).not.toHaveBeenCalled();
    vi.useRealTimers();
  });
});
