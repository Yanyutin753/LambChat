import { beforeEach, describe, expect, test, vi } from "vitest";
import {
  ensureScheduledTaskPrompt,
  getScheduledTaskPromptState,
  resetScheduledTaskPromptStoreForTests,
} from "../scheduledTaskPromptStore";
import { scheduledTaskApi } from "../../services/api/scheduledTask";
import type { ScheduledTask } from "../../types/scheduledTask";

vi.mock("../../services/api/scheduledTask", () => ({
  scheduledTaskApi: {
    get: vi.fn(),
  },
}));

function task(inputPayload: Record<string, unknown>): ScheduledTask {
  return {
    id: "task-1",
    name: "Numbers",
    input_payload: inputPayload,
  } as unknown as ScheduledTask;
}

beforeEach(() => {
  vi.clearAllMocks();
  resetScheduledTaskPromptStoreForTests();
});

describe("scheduledTaskPromptStore", () => {
  test("loads the task prompt once and caches it per task", async () => {
    vi.mocked(scheduledTaskApi.get).mockResolvedValue(
      task({ message: "Check whether AO3 is back" }),
    );
    await ensureScheduledTaskPrompt("task-1");
    await ensureScheduledTaskPrompt("task-1");
    expect(scheduledTaskApi.get).toHaveBeenCalledTimes(1);
    expect(getScheduledTaskPromptState()["task-1"]).toBe(
      "Check whether AO3 is back",
    );
  });

  test("falls back to the legacy prompt key", async () => {
    vi.mocked(scheduledTaskApi.get).mockResolvedValue(
      task({ prompt: "Legacy" }),
    );
    await ensureScheduledTaskPrompt("task-1");
    expect(getScheduledTaskPromptState()["task-1"]).toBe("Legacy");
  });

  test("a task without a prompt is remembered as absent without refetching", async () => {
    vi.mocked(scheduledTaskApi.get).mockResolvedValue(task({}));
    await ensureScheduledTaskPrompt("task-1");
    await ensureScheduledTaskPrompt("task-1");
    expect(scheduledTaskApi.get).toHaveBeenCalledTimes(1);
    expect(getScheduledTaskPromptState()["task-1"]).toBeUndefined();
  });

  test("a failed lookup retries on the next call", async () => {
    vi.mocked(scheduledTaskApi.get).mockRejectedValueOnce(new Error("offline"));
    await ensureScheduledTaskPrompt("task-1");
    expect(getScheduledTaskPromptState()["task-1"]).toBeUndefined();
    vi.mocked(scheduledTaskApi.get).mockResolvedValue(task({ message: "ok" }));
    await ensureScheduledTaskPrompt("task-1");
    expect(scheduledTaskApi.get).toHaveBeenCalledTimes(2);
    expect(getScheduledTaskPromptState()["task-1"]).toBe("ok");
  });
});
