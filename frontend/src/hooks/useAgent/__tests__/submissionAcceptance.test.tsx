/** @vitest-environment jsdom */

import { act, renderHook, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";

const { submitChat, connectToSSE } = vi.hoisted(() => ({
  submitChat: vi.fn(),
  connectToSSE: vi.fn(),
}));

vi.mock("../../useAuth", () => ({
  useAuth: () => ({ hasAnyPermission: () => false }),
}));

vi.mock("../../../services/api", () => ({
  sessionApi: {
    list: vi.fn(),
    markRead: vi.fn().mockResolvedValue(undefined),
    submitChat,
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
