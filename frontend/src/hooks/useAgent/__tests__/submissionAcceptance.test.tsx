/** @vitest-environment jsdom */

import { act, renderHook, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";

const { submitChat, connectToSSE, cancel } = vi.hoisted(() => ({
  submitChat: vi.fn(),
  connectToSSE: vi.fn(),
  cancel: vi.fn().mockResolvedValue(undefined),
}));

vi.mock("../../useAuth", () => ({
  useAuth: () => ({ hasAnyPermission: () => false }),
}));

vi.mock("../../../services/api", () => ({
  sessionApi: {
    list: vi.fn(),
    markRead: vi.fn().mockResolvedValue(undefined),
    submitChat,
    cancel,
    get: vi.fn(async (id: string) => ({
      id,
      name: "Other chat",
      metadata: {},
    })),
    getEvents: vi.fn().mockResolvedValue({ events: [] }),
    getPendingSteers: vi.fn().mockResolvedValue({ items: [] }),
    getPersistentGoal: vi.fn().mockResolvedValue({ goal: null }),
    getStatus: vi.fn().mockResolvedValue({ status: "completed" }),
    generateTitle: vi.fn().mockRejectedValue(new Error("skip title")),
  },
}));

vi.mock("../../../services/api/authenticatedRequest", () => ({
  authenticatedRequest: vi.fn().mockResolvedValue({
    ok: true,
    json: async () => ({
      agents: [{ id: "default", name: "Default" }],
      default_agent: "default",
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

vi.mock("../sseConnection", async () => {
  const actual =
    await vi.importActual<typeof import("../sseConnection")>(
      "../sseConnection",
    );
  return {
    ...actual,
    connectToSSE,
  };
});

import { useAgent } from "../../useAgent";
import { sessionApi } from "../../../services/api";
import {
  settleRemotelyTerminatedRun,
  type SSEConnectionContext,
} from "../sseConnection";

beforeEach(() => {
  vi.spyOn(console, "error").mockImplementation(() => undefined);
  submitChat.mockReset();
  submitChat.mockResolvedValue({
    session_id: "session-1",
    run_id: "run-1",
    trace_id: "trace-1",
    status: "started",
  });
  connectToSSE.mockReset();
  connectToSSE.mockResolvedValue(undefined);
  vi.mocked(sessionApi.get)
    .mockReset()
    .mockImplementation(
      async (id) =>
        ({
          id,
          name: "Other chat",
          metadata: {},
        }) as Awaited<ReturnType<typeof sessionApi.get>>,
    );
  vi.mocked(sessionApi.getEvents).mockReset().mockResolvedValue({ events: [] });
  vi.mocked(sessionApi.getStatus)
    .mockReset()
    .mockResolvedValue({ session_id: "session-a", status: "completed" });
  cancel.mockClear();
});

afterEach(() => {
  vi.restoreAllMocks();
});

test("accepted draft cleanup cannot turn an accepted POST into a send failure", async () => {
  const onRejected = vi.fn();
  const { result } = renderHook(() => useAgent());
  await waitFor(() => expect(result.current.currentAgent).toBe("default"));

  await act(async () => {
    await result.current.sendMessage("hello", undefined, undefined, undefined, {
      onAccepted: () => {
        throw new Error("cleanup exploded");
      },
      onRejected,
    });
  });

  expect(connectToSSE).toHaveBeenCalledTimes(1);
  expect(onRejected).not.toHaveBeenCalled();
  expect(result.current.error).toBeNull();
});

test("network rejection keeps the draft callback untouched", async () => {
  submitChat.mockRejectedValueOnce(new TypeError("Failed to fetch"));
  const onAccepted = vi.fn();
  const onRejected = vi.fn();
  const { result } = renderHook(() => useAgent());
  await waitFor(() => expect(result.current.currentAgent).toBe("default"));

  await act(async () => {
    await result.current.sendMessage(
      "keep draft",
      undefined,
      undefined,
      undefined,
      { onAccepted, onRejected },
    );
  });

  expect(onAccepted).not.toHaveBeenCalled();
  expect(onRejected).toHaveBeenCalledOnce();
  expect(result.current.error).not.toBeNull();
  expect(connectToSSE).not.toHaveBeenCalled();
});

test("invalid attachment rejection keeps the draft and exposes an actionable error", async () => {
  submitChat.mockRejectedValueOnce(new Error("invalid_attachments"));
  const onAccepted = vi.fn();
  const onRejected = vi.fn();
  const { result } = renderHook(() => useAgent());
  await waitFor(() => expect(result.current.currentAgent).toBe("default"));

  await act(async () => {
    await result.current.sendMessage(
      "keep attachment draft",
      undefined,
      undefined,
      undefined,
      { onAccepted, onRejected },
    );
  });

  expect(onAccepted).not.toHaveBeenCalled();
  expect(onRejected).toHaveBeenCalledOnce();
  expect(result.current.error).toBe(
    "One or more attachments are no longer available. Remove them and upload them again.",
  );
  expect(result.current.messages.at(-1)?.content).toBe(
    "Error: One or more attachments are no longer available. Remove them and upload them again.",
  );
  expect(connectToSSE).not.toHaveBeenCalled();
});

test.each(["started", "queued"])(
  "%s POST acceptance clears the draft exactly once",
  async (status) => {
    submitChat.mockResolvedValueOnce({
      session_id: "session-1",
      run_id: "run-1",
      trace_id: "trace-1",
      status,
      ...(status === "queued" ? { queue_position: 2 } : {}),
    });
    const onAccepted = vi.fn();
    const onRejected = vi.fn();
    const { result } = renderHook(() => useAgent());
    await waitFor(() => expect(result.current.currentAgent).toBe("default"));

    await act(async () => {
      await result.current.sendMessage(
        "accepted",
        undefined,
        undefined,
        undefined,
        { onAccepted, onRejected },
      );
    });

    expect(onAccepted).toHaveBeenCalledOnce();
    expect(onRejected).not.toHaveBeenCalled();
    expect(connectToSSE).toHaveBeenCalledOnce();
  },
);

test("a duplicate submit ignored while POST is pending cannot clear another draft", async () => {
  let resolveSubmit: ((value: Record<string, unknown>) => void) | undefined;
  submitChat.mockImplementationOnce(
    () =>
      new Promise((resolve) => {
        resolveSubmit = resolve;
      }),
  );
  const firstAccepted = vi.fn();
  const firstRejected = vi.fn();
  const duplicateAccepted = vi.fn();
  const duplicateRejected = vi.fn();
  const { result } = renderHook(() => useAgent());
  await waitFor(() => expect(result.current.currentAgent).toBe("default"));

  let firstSend: Promise<void> | undefined;
  await act(async () => {
    firstSend = result.current.sendMessage(
      "first",
      undefined,
      undefined,
      undefined,
      { onAccepted: firstAccepted, onRejected: firstRejected },
    );
  });
  await waitFor(() => expect(submitChat).toHaveBeenCalledOnce());

  await act(async () => {
    await result.current.sendMessage(
      "duplicate",
      undefined,
      undefined,
      undefined,
      { onAccepted: duplicateAccepted, onRejected: duplicateRejected },
    );
  });
  expect(duplicateAccepted).not.toHaveBeenCalled();
  expect(duplicateRejected).toHaveBeenCalledOnce();
  expect(submitChat).toHaveBeenCalledOnce();

  resolveSubmit?.({
    session_id: "session-1",
    run_id: "run-1",
    trace_id: "trace-1",
    status: "started",
  });
  await act(async () => {
    await firstSend;
  });
  expect(firstAccepted).toHaveBeenCalledOnce();
  expect(firstRejected).not.toHaveBeenCalled();
  expect(duplicateAccepted).not.toHaveBeenCalled();
});

test("a local goal validation error rejects the staged draft", async () => {
  const onAccepted = vi.fn();
  const onRejected = vi.fn();
  const { result } = renderHook(() => useAgent());
  await waitFor(() => expect(result.current.currentAgent).toBe("default"));

  await act(async () => {
    await result.current.sendMessage("/goal", undefined, undefined, undefined, {
      onAccepted,
      onRejected,
    });
  });

  expect(onAccepted).not.toHaveBeenCalled();
  expect(onRejected).toHaveBeenCalledOnce();
  expect(submitChat).not.toHaveBeenCalled();
});

test("background reconnect keeps the active bubble streaming after the old send exits", async () => {
  let releaseOldStream: () => void = () => undefined;
  connectToSSE.mockImplementationOnce((_session, _run, messageId, ctx) => {
    ctx.sseGenerationRef.current += 1;
    ctx.streamingMessageIdRef.current = messageId;
    return new Promise<void>((resolve) => {
      releaseOldStream = () => {
        ctx.sseGenerationRef.current += 1;
        resolve();
      };
    });
  });
  const { result } = renderHook(() => useAgent());
  await waitFor(() => expect(result.current.currentAgent).toBe("default"));
  let sending: Promise<void>;
  act(() => {
    sending = result.current.sendMessage("hello");
  });
  await waitFor(() => expect(connectToSSE).toHaveBeenCalledOnce());
  await act(async () => {
    releaseOldStream();
    await sending;
  });
  expect(
    result.current.messages.find((message) => message.role === "assistant")
      ?.isStreaming,
  ).toBe(true);
});

test("a remotely finished send reloads its full answer before the old stream exits", async () => {
  let streamContext!: SSEConnectionContext;
  let releaseStream!: () => void;
  connectToSSE.mockImplementationOnce((_session, _run, messageId, ctx) => {
    streamContext = ctx;
    ctx.sseGenerationRef.current += 1;
    ctx.streamingMessageIdRef.current = messageId;
    return new Promise<void>((resolve) => {
      releaseStream = resolve;
    });
  });
  vi.mocked(sessionApi.get).mockResolvedValueOnce({
    id: "session-1",
    agent_id: "default",
    created_at: "2026-10-15T00:00:00Z",
    updated_at: "2026-10-15T00:00:00Z",
    is_active: true,
    metadata: { current_run_id: "run-1" },
  });
  vi.mocked(sessionApi.getEvents).mockResolvedValueOnce({
    events: [
      {
        event_type: "user:message",
        run_id: "run-1",
        data: { content: "hello" },
      },
      {
        event_type: "message:chunk",
        run_id: "run-1",
        data: { content: "full answer from history" },
      },
      { event_type: "done", run_id: "run-1", data: {} },
    ],
  });
  const { result } = renderHook(() => useAgent());
  await waitFor(() => expect(result.current.currentAgent).toBe("default"));
  let sending!: Promise<void>;
  act(() => {
    sending = result.current.sendMessage("hello");
  });
  await waitFor(() => expect(connectToSSE).toHaveBeenCalledOnce());
  try {
    await act(async () => {
      settleRemotelyTerminatedRun(streamContext, "run-1", "run-1");
    });
    await waitFor(() =>
      expect(
        result.current.messages.some(
          (message) => message.content === "full answer from history",
        ),
      ).toBe(true),
    );
  } finally {
    await act(async () => {
      releaseStream();
      await sending;
    });
  }
});

function pendingSubmit() {
  let resolve!: (value: Record<string, unknown>) => void;
  const promise = new Promise<Record<string, unknown>>((done) => {
    resolve = done;
  });
  submitChat.mockReturnValueOnce(promise);
  return (session = "detached-session", run = "detached-run") =>
    resolve({
      session_id: session,
      run_id: run,
      trace_id: `trace-${run}`,
      status: "started",
    });
}

test.each([false, true])(
  "leaving during POST preserves accepted work without reattaching (existing chat=%s)",
  async (existing) => {
    const { result } = renderHook(() => useAgent());
    await waitFor(() => expect(result.current.currentAgent).toBe("default"));
    if (existing)
      await act(async () => {
        await result.current.sendMessage("previous turn");
      });
    connectToSSE.mockClear();
    const accept = pendingSubmit();
    const onAccepted = vi.fn();
    let sending!: Promise<void>;
    act(() => {
      sending = result.current.sendMessage(
        "continue working",
        undefined,
        undefined,
        undefined,
        { onAccepted },
      );
    });
    act(() => result.current.clearMessages());
    await act(async () => {
      accept();
      await sending;
    });
    expect(onAccepted).toHaveBeenCalledOnce();
    expect(cancel).not.toHaveBeenCalled();
    expect(connectToSSE).not.toHaveBeenCalled();
    expect(result.current.sessionId).toBeNull();
    expect(result.current.currentRunId).toBeNull();
    expect(result.current.messages).toEqual([]);
  },
);

test("a detached POST cannot reset flags or connect over a newer pending send", async () => {
  const { result } = renderHook(() => useAgent());
  await waitFor(() => expect(result.current.currentAgent).toBe("default"));
  const acceptOld = pendingSubmit();
  let oldSend!: Promise<void>;
  act(() => {
    oldSend = result.current.sendMessage("old task");
  });
  act(() => result.current.clearMessages());
  const acceptNew = pendingSubmit();
  let newSend!: Promise<void>;
  act(() => {
    newSend = result.current.sendMessage("new task");
  });
  await act(async () => {
    acceptOld();
    await oldSend;
  });
  expect(result.current.isLoading).toBe(true);
  expect(result.current.sessionId).toBeNull();
  expect(connectToSSE).not.toHaveBeenCalled();
  const rejected = vi.fn();
  await act(async () => {
    await result.current.sendMessage(
      "duplicate",
      undefined,
      undefined,
      undefined,
      { onAccepted: vi.fn(), onRejected: rejected },
    );
  });
  expect(rejected).toHaveBeenCalledOnce();
  expect(submitChat).toHaveBeenCalledTimes(2);
  await act(async () => {
    acceptNew("new-session", "new-run");
    await newSend;
  });
  expect(result.current.sessionId).toBe("new-session");
  expect(result.current.currentRunId).toBe("new-run");
  expect(connectToSSE).toHaveBeenCalledOnce();
});

test("background readiness excludes a previous run until the current POST is admitted", async () => {
  const { result } = renderHook(() => useAgent());
  await waitFor(() => expect(result.current.currentAgent).toBe("default"));
  await act(async () => {
    await result.current.sendMessage("previous turn");
  });
  expect(result.current.currentRunId).toBe("run-1");
  expect(result.current.canContinueInBackground).toBe(false);
  const accept = pendingSubmit();
  let releaseStream!: () => void;
  connectToSSE.mockImplementationOnce(
    () =>
      new Promise<void>((resolve) => {
        releaseStream = resolve;
      }),
  );
  let sending!: Promise<void>;
  act(() => {
    sending = result.current.sendMessage("next turn");
  });
  expect(result.current.isLoading).toBe(true);
  expect(result.current.currentRunId).toBeNull();
  expect(result.current.canContinueInBackground).toBe(false);
  await act(async () => {
    accept("session-1", "run-2");
  });
  expect(result.current.canContinueInBackground).toBe(true);
  expect(result.current.currentRunId).toBe("run-2");
  act(() => result.current.clearMessages());
  expect(result.current.canContinueInBackground).toBe(false);
  await act(async () => {
    releaseStream();
    await sending;
  });
  expect(cancel).not.toHaveBeenCalled();
});

test("unmount during POST cannot start a detached SSE subscription", async () => {
  const { result, unmount } = renderHook(() => useAgent());
  await waitFor(() => expect(result.current.currentAgent).toBe("default"));
  const accept = pendingSubmit();
  let sending!: Promise<void>;
  act(() => {
    sending = result.current.sendMessage("continue working");
  });
  unmount();
  await act(async () => {
    accept();
    await sending;
  });
  expect(connectToSSE).not.toHaveBeenCalled();
  expect(cancel).not.toHaveBeenCalled();
});

test("loading another chat revokes a pending POST before its admission returns", async () => {
  const { result } = renderHook(() => useAgent());
  await waitFor(() => expect(result.current.currentAgent).toBe("default"));
  const accept = pendingSubmit();
  let sending!: Promise<void>;
  act(() => {
    sending = result.current.sendMessage("continue working");
  });
  await act(async () => {
    await result.current.loadHistory("other-session");
  });
  await act(async () => {
    accept();
    await sending;
  });
  expect(result.current.sessionId).toBe("other-session");
  expect(result.current.currentRunId).toBeNull();
  expect(connectToSSE).not.toHaveBeenCalled();
  expect(cancel).not.toHaveBeenCalled();
});

test("a supplement cannot follow a pending cancellation into another chat", async () => {
  let releaseCancel!: () => void;
  cancel.mockImplementationOnce(
    () =>
      new Promise<void>((resolve) => {
        releaseCancel = resolve;
      }),
  );
  const { result } = renderHook(() => useAgent());
  await waitFor(() => expect(result.current.currentAgent).toBe("default"));
  await act(async () => {
    await result.current.loadHistory("session-a");
  });
  let supplement!: Promise<void>;
  act(() => {
    supplement = result.current.supplementFollowUp("A 的补充");
  });
  await act(async () => {
    await result.current.loadHistory("session-b");
  });
  await act(async () => {
    releaseCancel();
    await supplement;
  });
  expect(result.current.sessionId).toBe("session-b");
  expect(submitChat).not.toHaveBeenCalled();
  expect(result.current.messages).toEqual([]);
});

test("a failed cancellation does not submit the supplement concurrently", async () => {
  cancel.mockRejectedValueOnce(new Error("cancel unavailable"));
  vi.mocked(sessionApi.getStatus).mockResolvedValue({
    session_id: "session-a",
    status: "running",
  });
  const { result } = renderHook(() => useAgent());
  await waitFor(() => expect(result.current.currentAgent).toBe("default"));
  await act(async () => {
    await result.current.loadHistory("session-a");
  });
  await act(async () => {
    await result.current.supplementFollowUp("保留当前任务");
  });
  expect(submitChat).not.toHaveBeenCalled();
});

test("multiple follow-ups queued before session creation are admitted once in order", async () => {
  const { result } = renderHook(() => useAgent());
  await waitFor(() => expect(result.current.currentAgent).toBe("default"));
  const accept = pendingSubmit();
  submitChat.mockImplementation(async (_agent, content) => ({
    session_id: "session-a",
    run_id: `run-${content}`,
    trace_id: `trace-${content}`,
    status: "started",
  }));
  let sending!: Promise<void>;
  act(() => {
    sending = result.current.sendMessage("first");
  });
  act(() => {
    result.current.queueFollowUp("follow one");
    result.current.queueFollowUp("follow two");
  });
  await act(async () => {
    accept("session-a", "run-first");
    await sending;
  });
  await waitFor(() =>
    expect(submitChat.mock.calls.map((call) => call[1])).toEqual([
      "first",
      "follow one",
      "follow two",
    ]),
  );
  await waitFor(() => expect(result.current.steerMessages).toEqual([]));
});
