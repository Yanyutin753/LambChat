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
  const actual = await vi.importActual<typeof import("../sseConnection")>(
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
  const { result } = renderHook(() => useAgent());
  await waitFor(() => expect(result.current.currentAgent).toBe("default"));

  await act(async () => {
    await result.current.sendMessage("hello", undefined, undefined, undefined, {
      onAccepted: () => {
        throw new Error("cleanup exploded");
      },
    });
  });

  expect(connectToSSE).toHaveBeenCalledTimes(1);
  expect(result.current.error).toBeNull();
});

test.each([
  ["invalid attachment 422", new Error("Invalid or unavailable attachment")],
  ["network rejection", new TypeError("Failed to fetch")],
])("%s keeps the draft callback untouched", async (_name, rejection) => {
  submitChat.mockRejectedValueOnce(rejection);
  const onAccepted = vi.fn();
  const { result } = renderHook(() => useAgent());
  await waitFor(() => expect(result.current.currentAgent).toBe("default"));

  await act(async () => {
    await result.current.sendMessage(
      "keep draft",
      undefined,
      undefined,
      undefined,
      { onAccepted },
    );
  });

  expect(onAccepted).not.toHaveBeenCalled();
  expect(result.current.error).not.toBeNull();
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
    const { result } = renderHook(() => useAgent());
    await waitFor(() => expect(result.current.currentAgent).toBe("default"));

    await act(async () => {
      await result.current.sendMessage(
        "accepted",
        undefined,
        undefined,
        undefined,
        { onAccepted },
      );
    });

    expect(onAccepted).toHaveBeenCalledOnce();
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
  const duplicateAccepted = vi.fn();
  const { result } = renderHook(() => useAgent());
  await waitFor(() => expect(result.current.currentAgent).toBe("default"));

  let firstSend: Promise<void> | undefined;
  await act(async () => {
    firstSend = result.current.sendMessage(
      "first",
      undefined,
      undefined,
      undefined,
      { onAccepted: firstAccepted },
    );
  });
  await waitFor(() => expect(submitChat).toHaveBeenCalledOnce());

  await act(async () => {
    await result.current.sendMessage(
      "duplicate",
      undefined,
      undefined,
      undefined,
      { onAccepted: duplicateAccepted },
    );
  });
  expect(duplicateAccepted).not.toHaveBeenCalled();
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
  expect(duplicateAccepted).not.toHaveBeenCalled();
});
