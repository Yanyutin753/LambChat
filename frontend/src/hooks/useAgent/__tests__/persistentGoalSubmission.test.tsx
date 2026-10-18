/** @vitest-environment jsdom */
import { act, renderHook, waitFor } from "@testing-library/react";
import { vi } from "vitest";
const mocks = vi.hoisted(() => ({
  create: vi.fn(),
  put: vi.fn(),
  control: vi.fn(),
  submit: vi.fn(),
  get: vi.fn(),
  steer: vi.fn(),
  cancel: vi.fn(),
}));
vi.mock("../../useAuth", () => ({
  useAuth: () => ({ hasAnyPermission: () => false }),
}));
vi.mock("../../../services/api", () => ({
  sessionApi: {
    getPersistentGoal: mocks.get,
    create: mocks.create,
    putPersistentGoal: mocks.put,
    controlPersistentGoal: mocks.control,
    steer: mocks.steer,
    cancel: mocks.cancel,
    submitChat: mocks.submit,
    markRead: vi.fn().mockResolvedValue(undefined),
  },
}));
vi.mock("../../../services/api/authenticatedRequest", () => ({
  authenticatedRequest: vi.fn().mockResolvedValue({
    ok: true,
    json: async () => ({
      agents: [{ id: "fast", name: "Fast" }],
      default_agent: "fast",
      allowed_model_ids: null,
    }),
  }),
}));
vi.mock("../../../services/api/feedback", () => ({
  feedbackApi: { listBySession: vi.fn() },
}));
vi.mock("../../../services/api/tokenManager", () => ({
  getValidAccessToken: vi.fn().mockResolvedValue("token"),
}));
import { useAgent } from "../../useAgent";

const goal = {
  id: "g1",
  session_id: "s1",
  user_id: "u1",
  objective: "docs",
  rubric: "verified",
  revision: 1,
  version: 1,
  status: "paused",
  accounting: { turns: 0, tokens: null },
  started_at: null,
  current_run_id: null,
};

test("persistent command creates a session then explicit goal API without submitting ordinary chat", async () => {
  mocks.create.mockResolvedValue({ id: "s1", metadata: {}, agent_id: "fast" });
  mocks.put.mockResolvedValue({ goal });
  const { result } = renderHook(() => useAgent());
  await waitFor(() => expect(result.current.currentAgent).toBe("fast"));
  const accepted = vi.fn();
  await act(async () => {
    await result.current.sendMessage(
      "/goal persist docs\n---\nverified",
      undefined,
      undefined,
      undefined,
      { onAccepted: accepted },
    );
  });
  expect(mocks.create).toHaveBeenCalledOnce();
  expect(mocks.put).toHaveBeenCalledWith(
    "s1",
    expect.objectContaining({ objective: "docs", rubric: "verified" }),
  );
  expect(mocks.submit).not.toHaveBeenCalled();
  expect(result.current.persistentGoal?.objective).toBe("docs");
  expect(accepted).toHaveBeenCalledOnce();
});

test("rejected persistent mutation preserves draft and does not invent active state", async () => {
  mocks.create.mockResolvedValue({ id: "s1", metadata: {}, agent_id: "fast" });
  mocks.put.mockRejectedValue(new Error("Goal changed; refresh and retry"));
  const { result } = renderHook(() => useAgent());
  await waitFor(() => expect(result.current.currentAgent).toBe("fast"));
  const accepted = vi.fn();
  const rejected = vi.fn();
  await act(async () => {
    await result.current.sendMessage(
      "/goal persist docs",
      undefined,
      undefined,
      undefined,
      { onAccepted: accepted, onRejected: rejected },
    );
  });
  expect(accepted).not.toHaveBeenCalled();
  expect(rejected).toHaveBeenCalledOnce();
  expect(result.current.persistentGoal).toBeNull();
});

test("leaving an empty conversation during session creation cannot attach the late goal", async () => {
  let resolveCreate!: (value: {
    id: string;
    metadata: Record<string, unknown>;
    agent_id: string;
  }) => void;
  mocks.create.mockReturnValueOnce(
    new Promise((resolve) => {
      resolveCreate = resolve;
    }),
  );
  const { result } = renderHook(() => useAgent());
  await waitFor(() => expect(result.current.currentAgent).toBe("fast"));
  const callsBefore = mocks.put.mock.calls.length;
  const rejected = vi.fn();
  let sending!: Promise<void>;
  act(() => {
    sending = result.current.sendMessage(
      "/goal persist docs",
      undefined,
      undefined,
      undefined,
      { onRejected: rejected },
    );
  });
  act(() => result.current.clearMessages());
  await act(async () => {
    resolveCreate({ id: "late-session", metadata: {}, agent_id: "fast" });
    await sending;
  });
  expect(result.current.sessionId).toBeNull();
  expect(result.current.persistentGoal).toBeNull();
  expect(mocks.put.mock.calls.length).toBe(callsBefore);
  expect(rejected).toHaveBeenCalledOnce();
});

test("persistent commands reject attachments without silently clearing their draft", async () => {
  const { result } = renderHook(() => useAgent());
  await waitFor(() => expect(result.current.currentAgent).toBe("fast"));
  const accepted = vi.fn();
  const rejected = vi.fn();
  const callsBefore = mocks.put.mock.calls.length;
  await act(async () => {
    await result.current.sendMessage(
      "/goal persist docs",
      undefined,
      [{ id: "file-1" } as import("../../../types").MessageAttachment],
      undefined,
      { onAccepted: accepted, onRejected: rejected },
    );
  });
  expect(accepted).not.toHaveBeenCalled();
  expect(rejected).toHaveBeenCalledOnce();
  expect(mocks.put.mock.calls.length).toBe(callsBefore);
});

test("late control response cannot replace newer displayed goal revision", async () => {
  mocks.create.mockResolvedValue({ id: "s1", metadata: {}, agent_id: "fast" });
  mocks.put.mockResolvedValue({ goal: { ...goal, revision: 5 } });
  mocks.control.mockResolvedValue({
    goal: { ...goal, revision: 4, objective: "obsolete" },
  });
  const { result } = renderHook(() => useAgent());
  await waitFor(() => expect(result.current.currentAgent).toBe("fast"));
  await act(async () => {
    await result.current.sendMessage("/goal persist docs");
  });
  await act(async () => {
    await result.current.controlPersistentGoal("resume");
  });
  expect(result.current.persistentGoal?.revision).toBe(5);
  expect(result.current.persistentGoal?.objective).toBe("docs");
});

test.each(["cleared", "paused", "completed"])(
  "ordinary /goal clear preserves %s persistent revision",
  async (status) => {
    mocks.create.mockResolvedValue({
      id: "s1",
      metadata: {},
      agent_id: "fast",
    });
    mocks.put.mockResolvedValue({ goal: { ...goal, status, revision: 8 } });
    mocks.submit.mockRejectedValue(
      new Error("isolated transport stopped after local goal selection"),
    );
    const { result } = renderHook(() => useAgent());
    await waitFor(() => expect(result.current.currentAgent).toBe("fast"));
    await act(async () => {
      await result.current.sendMessage("/goal persist docs");
    });
    await act(async () => {
      await result.current.sendMessage("/goal run docs\n---\nverified");
    });
    expect(result.current.activeGoal?.objective).toBe("docs");
    const controlsBefore = mocks.control.mock.calls.length;
    await act(async () => {
      await result.current.sendMessage("/goal clear");
    });
    expect(result.current.activeGoal).toBeNull();
    expect(mocks.control.mock.calls.length).toBe(controlsBefore);
    expect(result.current.persistentGoal?.revision).toBe(8);
  },
);

test("unavailable persistent status backs off and hidden pages stop polling", async () => {
  mocks.create.mockResolvedValue({ id: "s1", metadata: {}, agent_id: "fast" });
  mocks.put.mockResolvedValue({ goal: { ...goal, status: "active" } });
  mocks.get.mockRejectedValue(new Error("network unavailable"));
  const warn = vi.spyOn(console, "warn").mockImplementation(() => undefined);
  const { result, unmount } = renderHook(() => useAgent());
  await waitFor(() => expect(result.current.currentAgent).toBe("fast"));
  vi.useFakeTimers();
  const before = mocks.get.mock.calls.length;
  try {
    await act(async () => {
      await result.current.sendMessage("/goal persist docs");
    });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(3000);
    });
    expect(mocks.get.mock.calls.length - before).toBe(1);
    await act(async () => {
      await vi.advanceTimersByTimeAsync(3000);
    });
    expect(mocks.get.mock.calls.length - before).toBe(2);
    Object.defineProperty(document, "visibilityState", {
      configurable: true,
      value: "hidden",
    });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(60000);
    });
    expect(mocks.get.mock.calls.length - before).toBe(2);
    Object.defineProperty(document, "visibilityState", {
      configurable: true,
      value: "visible",
    });
    await act(async () => {
      document.dispatchEvent(new Event("visibilitychange"));
    });
    expect(mocks.get.mock.calls.length - before).toBe(3);
  } finally {
    unmount();
    Object.defineProperty(document, "visibilityState", {
      configurable: true,
      value: "visible",
    });
    vi.useRealTimers();
    warn.mockRestore();
  }
});

test.each(["/goal docs", "toolbar"])(
  "%s creates a persistent goal by default",
  async (entry) => {
    mocks.create.mockResolvedValue({
      id: "s1",
      metadata: {},
      agent_id: "fast",
    });
    mocks.put.mockResolvedValue({ goal });
    const { result, unmount } = renderHook(() => useAgent());
    await waitFor(() => expect(result.current.currentAgent).toBe("fast"));
    if (entry === "toolbar") act(() => result.current.setGoalModeEnabled(true));
    const before = mocks.put.mock.calls.length;
    await act(async () => {
      await result.current.sendMessage(entry === "toolbar" ? "docs" : entry);
    });
    expect(mocks.put.mock.calls.length).toBe(before + 1);
    expect(result.current.persistentGoal?.id).toBe("g1");
    unmount();
  },
);

test("guiding an active Goal enqueues a steer without cancelling or pausing it", async () => {
  const active = { ...goal, status: "active", current_run_id: null };
  mocks.create.mockResolvedValue({ id: "s1", metadata: {}, agent_id: "fast" });
  mocks.put.mockResolvedValue({ goal: active });
  mocks.get.mockResolvedValue({ goal: active });
  mocks.steer.mockResolvedValue({ status: "queued", outcome: "accepted" });
  const cancellations = mocks.cancel.mock.calls.length;
  const submissions = mocks.submit.mock.calls.length;
  const { result, unmount } = renderHook(() => useAgent());
  await waitFor(() => expect(result.current.currentAgent).toBe("fast"));
  await act(async () => {
    await result.current.sendMessage("/goal persist docs");
  });
  await act(async () => {
    await result.current.supplementFollowUp("owner Xiaolin");
  });
  expect(mocks.steer).toHaveBeenCalledWith(
    "s1",
    "owner Xiaolin",
    expect.any(String),
    [],
  );
  expect(mocks.cancel.mock.calls.length).toBe(cancellations);
  expect(mocks.submit.mock.calls.length).toBe(submissions);
  expect(result.current.persistentGoal?.status).toBe("active");
  unmount();
});
