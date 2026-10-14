/** @vitest-environment jsdom */
import { act, renderHook, waitFor } from "@testing-library/react";
import { beforeEach, expect, test, vi } from "vitest";

const mocks = vi.hoisted(() => ({ get: vi.fn(), events: vi.fn(), connect: vi.fn(), goal: vi.fn(), steers: vi.fn() }));
vi.mock("../../useAuth", () => ({ useAuth: () => ({ hasAnyPermission: () => false }) }));
vi.mock("../../../services/api", () => ({ sessionApi: {
  get: mocks.get, getEvents: mocks.events,
  markRead: vi.fn().mockResolvedValue(undefined),
  getPendingSteers: mocks.steers,
  getPersistentGoal: mocks.goal,
} }));
vi.mock("../../../services/api/authenticatedRequest", () => ({ authenticatedRequest: vi.fn().mockResolvedValue({ ok: true, json: async () => ({ agents: [{ id: "fast", name: "Fast" }], default_agent: "fast", allowed_model_ids: null }) }) }));
vi.mock("../../../services/api/feedback", () => ({ feedbackApi: { listBySession: vi.fn() } }));
vi.mock("../../../services/api/tokenManager", () => ({ getValidAccessToken: vi.fn().mockResolvedValue("token") }));
vi.mock("../sseConnection", async () => ({ ...await vi.importActual<typeof import("../sseConnection")>("../sseConnection"), connectToSSE: mocks.connect }));
import { useAgent } from "../../useAgent";
import * as historyFetch from "../../../services/api/fetch";

function events(run: string, timestamp: string) {
  return [
    { id: `${run}-user`, event_type: "user:message", run_id: run, timestamp, data: { content: `question-${run}` } },
    { id: `${run}-answer`, event_type: "message:chunk", run_id: run, timestamp, data: { content: `answer-${run}` } },
  ];
}
const latestWindow = () => ({ events: events("new-run", "2026-10-13T10:00:00Z"), stream_run_id: "new-run", has_more_traces: true, trace_window: { oldest_trace_started_at: "2026-10-13T10:00:00Z", oldest_trace_id: "new-trace" } });
let liveController: AbortController;
beforeEach(() => {
  mocks.steers.mockReset().mockResolvedValue({ items: [] });
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

test("complete history is visible while optional steers and goal are pending without reconnecting early", async () => {
  let resolveSteers!: (value: { items: [] }) => void;
  let resolveGoal!: (value: { goal: null }) => void;
  mocks.steers.mockImplementationOnce(() => new Promise(resolve => { resolveSteers = resolve; }));
  mocks.goal.mockImplementationOnce(() => new Promise(resolve => { resolveGoal = resolve; }));
  const { result } = renderHook(() => useAgent());
  let loading!: Promise<unknown>;
  act(() => { loading = result.current.loadHistory("s1"); });
  await waitFor(() => expect(result.current.messages.map(message => message.content)).toEqual(["question-new-run", "answer-new-run"]));
  expect(result.current.hasMoreHistoryTraces).toBe(true);
  expect(result.current.isLoadingHistory).toBe(true);
  expect(mocks.connect).not.toHaveBeenCalled();
  await act(async () => { resolveSteers({ items: [] }); resolveGoal({ goal: null }); await loading; });
  expect(result.current.isLoadingHistory).toBe(false);
  expect(mocks.connect).toHaveBeenCalledOnce();
});

test("an old optional response cannot overwrite a newer session after primary history was displayed", async () => {
  let resolveSteers!: (value: { items: [] }) => void;
  mocks.steers.mockImplementationOnce(() => new Promise(resolve => { resolveSteers = resolve; }));
  const { result } = renderHook(() => useAgent());
  let oldLoad!: Promise<unknown>;
  act(() => { oldLoad = result.current.loadHistory("s1"); });
  await waitFor(() => expect(result.current.messages).toHaveLength(2));
  mocks.events.mockImplementationOnce(async () => ({ events: events("other-run", "2026-10-15T10:00:00Z") }));
  await act(async () => { await result.current.loadHistory("s2"); });
  await act(async () => { resolveSteers({ items: [] }); await oldLoad; });
  expect(result.current.sessionId).toBe("s2");
  expect(result.current.messages.map(message => message.runId)).toEqual(["other-run", "other-run"]);
  expect(mocks.connect).not.toHaveBeenCalled();
});

test("switching starts pending steers and goal reads alongside the full history window", async () => {
  let resolveEvents!: (value: ReturnType<typeof latestWindow>) => void;
  mocks.events.mockImplementationOnce(() => new Promise(done => { resolveEvents = done; }));
  const { result } = renderHook(() => useAgent());
  let pending!: Promise<unknown>;
  act(() => { pending = result.current.loadHistory("s1"); });
  try {
    await waitFor(() => {
      expect(mocks.steers).toHaveBeenCalledWith("s1", expect.objectContaining({ signal: expect.any(AbortSignal) }));
      expect(mocks.goal).toHaveBeenCalledWith("s1", expect.objectContaining({ signal: expect.any(AbortSignal) }));
    });
  } finally {
    await act(async () => { resolveEvents(latestWindow()); await pending; });
  }
  expect(result.current.messages.some(message => message.content === "question-new-run")).toBe(true);
  expect(result.current.messages.some(message => message.content === "answer-new-run")).toBe(true);
  expect(result.current.hasMoreHistoryTraces).toBe(true);
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


test("history pages prefetch approval metadata and retain previous-page statuses without per-approval reads", async () => {
  const lookup = vi.spyOn(historyFetch, "authFetch").mockResolvedValue(null);
  const approval = (run: string) => ({ event_type: "approval_required", run_id: run, timestamp: run === "old-run" ? "2026-10-01T10:00:00Z" : "2026-10-13T10:00:00Z", data: { id: `approval-${run}`, message: "confirm" } });
  const status = (run: string) => ({ id: `approval-${run}`, status: "approved", metadata: { approval_type: "scheduled_task_create" } });
  mocks.events.mockImplementation(async (_id: string, options: { before_trace_id?: string }) => options.before_trace_id ? {
    events: [...events("old-run", "2026-10-01T10:00:00Z"), approval("old-run")],
    approval_statuses: { "approval-old-run": status("old-run") },
    has_more_traces: false, trace_window: null,
  } : {
    ...latestWindow(), events: [...latestWindow().events, approval("new-run")],
    approval_statuses: { "approval-new-run": status("new-run") },
  });
  try {
    const { result } = renderHook(() => useAgent());
    await act(async () => { await result.current.loadHistory("s1"); });
    await act(async () => { await result.current.loadOlderHistory(); });
    expect(mocks.events).toHaveBeenCalledTimes(2);
    for (const call of mocks.events.mock.calls) expect(call[1]).toEqual(expect.objectContaining({ include_approval_statuses: true }));
    expect(lookup).not.toHaveBeenCalled();
    for (const run of ["new-run", "old-run"]) {
      expect(result.current.messages.some(message => message.content === `question-${run}`)).toBe(true);
      const assistant = result.current.messages.find(message => message.role === "assistant" && message.runId === run);
      expect(assistant?.parts?.find(part => part.type === "tool" && part.id === `approval-${run}`)).toMatchObject({ isPending: false, success: true });
    }
  } finally { lookup.mockRestore(); }
});
