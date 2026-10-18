/** @vitest-environment jsdom */
import { act, renderHook, waitFor } from "@testing-library/react";
import { vi } from "vitest";
import type { PersistentGoal } from "../../../services/api/session";

const getGoal = vi.hoisted(() => vi.fn());
const updateGoal = vi.hoisted(() => vi.fn());
vi.mock("../../../services/api", () => ({
  sessionApi: { getPersistentGoal: getGoal, updatePersistentGoal: updateGoal },
}));
import { usePersistentGoalRuntime } from "../persistentGoalRuntime";

test("a goal that finishes between polls still reloads its final messages", async () => {
  const goal: PersistentGoal = {
    id: "g",
    session_id: "s",
    user_id: "u",
    objective: "finish",
    rubric: "verified",
    version: 1,
    revision: 1,
    status: "active",
    current_run_id: null,
    started_at: null,
    accounting: { turns: 0, tokens: 0 },
  };
  getGoal.mockResolvedValue({
    goal: {
      ...goal,
      revision: 3,
      status: "completed",
      accounting: { turns: 1, tokens: 50 },
    },
  });
  const load = vi.fn().mockResolvedValue(undefined);
  const { unmount } = renderHook(() =>
    usePersistentGoalRuntime({
      sessionId: "s",
      persistentGoal: goal,
      setPersistentGoalState: vi.fn(),
      setPersistentGoalBusy: vi.fn(),
      setError: vi.fn(),
      sessionIdRef: { current: "s" },
      currentRunIdRef: { current: null },
      isSendingRef: { current: false },
      isLoadingHistoryRef: { current: false },
      loadHistoryRef: { current: load },
    }),
  );
  await waitFor(() => expect(getGoal).toHaveBeenCalled());
  await act(async () => {});
  expect(load).toHaveBeenCalledWith("s");
  unmount();
});

test("paused Goal reconciles cancellation usage that is still settling", async () => {
  getGoal.mockClear();
  const goal = {
    id: "g",
    session_id: "s",
    user_id: "u",
    objective: "finish",
    rubric: "verified",
    version: 2,
    revision: 4,
    status: "paused",
    current_run_id: null,
    started_at: null,
    accounting: { turns: 0, tokens: 0 },
    run_accounting: [{ run_id: "r", completed: false }],
  } as PersistentGoal;
  const settled = {
    ...goal,
    revision: 5,
    accounting: { turns: 1, tokens: null },
    run_accounting: [{ run_id: "r", completed: true }],
  };
  getGoal.mockResolvedValue({ goal: settled });
  const setGoal = vi.fn();
  const load = vi.fn().mockResolvedValue(undefined);
  const { unmount } = renderHook(() =>
    usePersistentGoalRuntime({
      sessionId: "s",
      persistentGoal: goal,
      setPersistentGoalState: setGoal,
      setPersistentGoalBusy: vi.fn(),
      setError: vi.fn(),
      sessionIdRef: { current: "s" },
      currentRunIdRef: { current: "r" },
      isSendingRef: { current: false },
      isLoadingHistoryRef: { current: false },
      loadHistoryRef: { current: load },
    }),
  );
  await waitFor(() => expect(getGoal).toHaveBeenCalled());
  expect(setGoal).toHaveBeenCalledWith(settled);
  expect(load).toHaveBeenCalledWith("s");
  unmount();
});

test("a continuation reconciles the session instead of opening a read-only history target", async () => {
  getGoal.mockClear();
  const goal: PersistentGoal = {
    id: "g",
    session_id: "s",
    user_id: "u",
    objective: "finish",
    rubric: "verified",
    version: 1,
    revision: 1,
    status: "active",
    current_run_id: null,
    started_at: null,
    accounting: { turns: 1, tokens: 200 },
  };
  getGoal.mockResolvedValue({
    goal: { ...goal, revision: 2, current_run_id: "goal-next" },
  });
  const load = vi.fn().mockResolvedValue(undefined);
  const { unmount } = renderHook(() =>
    usePersistentGoalRuntime({
      sessionId: "s",
      persistentGoal: goal,
      setPersistentGoalState: vi.fn(),
      setPersistentGoalBusy: vi.fn(),
      setError: vi.fn(),
      sessionIdRef: { current: "s" },
      currentRunIdRef: { current: "goal-previous" },
      isSendingRef: { current: false },
      isLoadingHistoryRef: { current: false },
      loadHistoryRef: { current: load },
    }),
  );
  await waitFor(() => expect(load).toHaveBeenCalledWith("s"));
  unmount();
});

test("editing reconciles the authoritative Goal and keeps a failed edit retryable", async () => {
  const goal = {
    id: "g",
    session_id: "s",
    user_id: "u",
    objective: "old",
    rubric: "criteria",
    version: 1,
    revision: 3,
    status: "paused",
    current_run_id: null,
    started_at: null,
    accounting: { turns: 4, tokens: 150000 },
  } as PersistentGoal;
  const saved = { ...goal, objective: "new", version: 2, revision: 4 };
  updateGoal
    .mockResolvedValueOnce({ goal: saved })
    .mockRejectedValueOnce(new Error("conflict"));
  const setGoal = vi.fn();
  const error = vi.fn();
  const { result, unmount } = renderHook(() =>
    usePersistentGoalRuntime({
      sessionId: "s",
      persistentGoal: goal,
      setPersistentGoalState: setGoal,
      setPersistentGoalBusy: vi.fn(),
      setError: error,
      sessionIdRef: { current: "s" },
      currentRunIdRef: { current: null },
      isSendingRef: { current: false },
      isLoadingHistoryRef: { current: false },
      loadHistoryRef: { current: vi.fn() },
    }),
  );
  await act(async () => {
    expect(
      await result.current.updatePersistentGoal("new", "criteria", 3),
    ).toBe(true);
  });
  expect(updateGoal).toHaveBeenCalledWith("s", {
    objective: "new",
    rubric: "criteria",
    expected_revision: 3,
  });
  expect(setGoal).toHaveBeenCalledWith(saved);
  await act(async () => {
    expect(
      await result.current.updatePersistentGoal("draft", "criteria", 3),
    ).toBe(false);
  });
  expect(error).toHaveBeenLastCalledWith("conflict");
  unmount();
});

test("an in-flight goal poll cannot reload history over a newly submitted user turn", async () => {
  let release!: (value: unknown) => void;
  getGoal.mockReturnValueOnce(
    new Promise((resolve) => {
      release = resolve;
    }),
  );
  const goal = {
    id: "g",
    session_id: "s",
    user_id: "u",
    objective: "finish",
    rubric: "verified",
    version: 1,
    revision: 1,
    status: "active",
    current_run_id: null,
    started_at: null,
    accounting: { turns: 0, tokens: 0 },
  } as PersistentGoal;
  const sending = { current: false };
  const load = vi.fn();
  const setGoal = vi.fn();
  const { unmount } = renderHook(() =>
    usePersistentGoalRuntime({
      sessionId: "s",
      persistentGoal: goal,
      setPersistentGoalState: setGoal,
      setPersistentGoalBusy: vi.fn(),
      setError: vi.fn(),
      sessionIdRef: { current: "s" },
      currentRunIdRef: { current: "human-turn" },
      isSendingRef: sending,
      isLoadingHistoryRef: { current: false },
      loadHistoryRef: { current: load },
    }),
  );
  sending.current = true;
  await act(async () => {
    release({ goal: { ...goal, revision: 2, current_run_id: "goal-old" } });
  });
  expect(load).not.toHaveBeenCalled();
  expect(setGoal).not.toHaveBeenCalled();
  unmount();
});
