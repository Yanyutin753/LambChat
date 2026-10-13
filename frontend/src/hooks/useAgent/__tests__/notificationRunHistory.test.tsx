/** @vitest-environment jsdom */
import { act, renderHook, waitFor } from "@testing-library/react";
import { beforeEach, expect, test, vi } from "vitest";

const mocks = vi.hoisted(() => ({ get: vi.fn(), events: vi.fn(), connect: vi.fn(), goal: vi.fn() }));
vi.mock("../../useAuth", () => ({ useAuth: () => ({ hasAnyPermission: () => false }) }));
vi.mock("../../../services/api", () => ({ sessionApi: {
  get: mocks.get, getEvents: mocks.events,
  markRead: vi.fn().mockResolvedValue(undefined),
  getPendingSteers: vi.fn().mockResolvedValue({ items: [] }),
  getPersistentGoal: mocks.goal,
} }));
vi.mock("../../../services/api/authenticatedRequest", () => ({ authenticatedRequest: vi.fn().mockResolvedValue({ ok: true, json: async () => ({ agents: [{ id: "fast", name: "Fast" }], default_agent: "fast", allowed_model_ids: null }) }) }));
vi.mock("../../../services/api/feedback", () => ({ feedbackApi: { listBySession: vi.fn() } }));
vi.mock("../../../services/api/tokenManager", () => ({ getValidAccessToken: vi.fn().mockResolvedValue("token") }));
vi.mock("../sseConnection", async () => ({ ...await vi.importActual<typeof import("../sseConnection")>("../sseConnection"), connectToSSE: mocks.connect }));
import { useAgent } from "../../useAgent";

function events(run: string, timestamp: string) {
  return [
    { id: `${run}-user`, event_type: "user:message", run_id: run, timestamp, data: { content: `question-${run}` } },
    { id: `${run}-answer`, event_type: "message:chunk", run_id: run, timestamp, data: { content: `answer-${run}` } },
  ];
}
const latestWindow = () => ({ events: events("new-run", "2026-10-13T10:00:00Z"), stream_run_id: "new-run", has_more_traces: true, trace_window: { oldest_trace_started_at: "2026-10-13T10:00:00Z", oldest_trace_id: "new-trace" } });
let liveController: AbortController;
beforeEach(() => {
  mocks.goal.mockReset().mockResolvedValue({ goal: null });
  mocks.get.mockReset().mockImplementation(async (id: string) => ({ id, metadata: { current_run_id: "new-run", task_status: "running" } }));
  mocks.events.mockReset().mockImplementation(async (_id: string, options: { run_id?: string }) => options.run_id
    ? { events: events(options.run_id, "2026-10-01T10:00:00Z") }
    : latestWindow());
  mocks.connect.mockReset().mockImplementation(async (_session: string, _run: string, _message: string, ctx: { abortControllerRef: { current: AbortController | null } }) => {
    liveController = new AbortController();
    ctx.abortControllerRef.current = liveController;
  });
});

test("initial old-run deep link reads the exact run once alongside the recent window", async () => {
  const { result } = renderHook(() => useAgent());
  await act(async () => { await result.current.loadHistory("s1", "old-run"); });
  expect(mocks.events).toHaveBeenCalledWith("s1", expect.objectContaining({ run_id: "old-run", compact_message_chunks: true }));
  expect(mocks.events).toHaveBeenCalledTimes(2);
  expect(result.current.messages.some(message => message.runId === "old-run")).toBe(true);
  expect(result.current.messages.some(message => message.runId === "new-run")).toBe(true);
  expect(result.current.hasMoreHistoryTraces).toBe(true);
});

test("same-session missing notification run is merged without aborting the live run or resetting its pagination", async () => {
  const { result } = renderHook(() => useAgent());
  await act(async () => { await result.current.loadHistory("s1"); });
  await waitFor(() => expect(mocks.connect).toHaveBeenCalledOnce());
  const originalController = liveController;
  mocks.events.mockClear();
  mocks.get.mockClear();
  await act(async () => { await result.current.loadHistory("s1", "old-run"); });
  expect(mocks.events).toHaveBeenCalledTimes(1);
  expect(mocks.events).toHaveBeenCalledWith("s1", expect.objectContaining({ run_id: "old-run" }));
  expect(mocks.get).not.toHaveBeenCalled();
  expect(originalController.signal.aborted).toBe(false);
  expect(mocks.connect).toHaveBeenCalledOnce();
  expect(result.current.messages.some(message => message.runId === "old-run")).toBe(true);
  expect(result.current.messages.find(message => message.role === "assistant" && message.runId === "new-run")?.isStreaming).toBe(true);
  expect(result.current.hasMoreHistoryTraces).toBe(true);
});

test("same-session notification for an already loaded run does not refetch or reconnect", async () => {
  const { result } = renderHook(() => useAgent());
  await act(async () => { await result.current.loadHistory("s1"); });
  const originalController = liveController;
  mocks.events.mockClear();
  mocks.get.mockClear();
  await act(async () => { await result.current.loadHistory("s1", "new-run"); });
  expect(mocks.events).not.toHaveBeenCalled();
  expect(mocks.get).not.toHaveBeenCalled();
  expect(originalController.signal.aborted).toBe(false);
  expect(mocks.connect).toHaveBeenCalledOnce();
});

test("Goal polling that discovers a new admitted run still restores its current SSE owner", async () => {
  const goal = { id: "g1", session_id: "s1", user_id: "u1", status: "active", objective: "task", rubric: "verified", revision: 1, version: 1, current_run_id: "new-run" };
  mocks.goal.mockResolvedValueOnce({ goal }).mockResolvedValue({ goal: { ...goal, revision: 2, current_run_id: "goal-run" } });
  mocks.get.mockResolvedValueOnce({ id: "s1", metadata: { current_run_id: "new-run" } }).mockResolvedValue({ id: "s1", metadata: { current_run_id: "goal-run" } });
  mocks.events.mockResolvedValueOnce(latestWindow()).mockResolvedValue({ ...latestWindow(), events: events("goal-run", "2026-10-13T11:00:00Z"), stream_run_id: "goal-run" });
  const { result } = renderHook(() => useAgent());
  await act(async () => { await result.current.loadHistory("s1"); });
  await waitFor(() => expect(mocks.connect).toHaveBeenCalledTimes(2));
  expect(mocks.connect.mock.calls[1][1]).toBe("goal-run");
});

test("late exact-run reply after changing sessions cannot insert the previous session's target", async () => {
  const { result } = renderHook(() => useAgent());
  await act(async () => { await result.current.loadHistory("s1"); });
  let resolve!: (value: { events: ReturnType<typeof events> }) => void;
  mocks.events.mockImplementationOnce(() => new Promise(done => { resolve = done; }));
  let pending!: Promise<unknown>;
  act(() => { pending = result.current.loadHistory("s1", "old-run"); });
  await act(async () => { await result.current.loadHistory("s2"); });
  await act(async () => { resolve({ events: events("old-run", "2026-10-01T10:00:00Z") }); await pending; });
  expect(result.current.sessionId).toBe("s2");
  expect(result.current.messages.some(message => message.runId === "old-run")).toBe(false);
});
