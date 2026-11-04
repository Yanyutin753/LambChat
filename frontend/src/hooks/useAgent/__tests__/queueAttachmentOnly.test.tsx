/** @vitest-environment jsdom */
import { act, renderHook, waitFor } from "@testing-library/react";
import { beforeEach, expect, test, vi } from "vitest";
import type { Message, MessageAttachment } from "../../../types";
import type { EventHandlerContext } from "../eventHandlers";
import { handleStreamEvent } from "../eventHandlers";
import { useAgent } from "../../useAgent";
import { useSteerQueue } from "../steerQueue";

const api = vi.hoisted(() => ({ submitChat: vi.fn(), steer: vi.fn() }));
vi.mock("../../useAuth", () => ({ useAuth: () => ({ hasAnyPermission: () => false }) }));
vi.mock("../../../services/api", () => ({ sessionApi: {
  ...api, list: vi.fn(), markRead: vi.fn(), cancel: vi.fn(),
  get: vi.fn(async (id: string) => ({ id, name: "Chat", metadata: {} })),
  getEvents: vi.fn(async () => ({ events: [] })),
  getPendingSteers: vi.fn(async () => ({ items: [] })),
  getPersistentGoal: vi.fn(async () => ({ goal: null })),
  getStatus: vi.fn(async () => ({ status: "completed" })),
  generateTitle: vi.fn(async () => ({})),
} }));
vi.mock("../../../services/api/authenticatedRequest", () => ({ authenticatedRequest: vi.fn(async () => ({
  ok: true, json: async () => ({ agents: [{ id: "default", name: "Default" }], default_agent: "default", allowed_model_ids: null }),
})) }));
vi.mock("../../../services/api/feedback", () => ({ feedbackApi: { listBySession: vi.fn() } }));
vi.mock("../../../services/api/tokenManager", () => ({ getValidAccessToken: vi.fn(async () => "token") }));
vi.mock("../sseConnection", async () => ({
  ...await vi.importActual<typeof import("../sseConnection")>("../sseConnection"),
  connectToSSE: vi.fn(async () => undefined),
}));

const attachment: MessageAttachment = {
  id: "image-1", key: "uploads/image-1", name: "截图.png", type: "image",
  mimeType: "image/png", size: 100, url: "/api/files/image-1",
};
beforeEach(() => {
  sessionStorage.clear();
  vi.clearAllMocks();
  api.submitChat.mockResolvedValue({ session_id: "s1", run_id: "r1", trace_id: "t1", status: "pending" });
  api.steer.mockResolvedValue({ status: "queued", message_id: "queued-image" });
});

test("an attachment-only queued message is submitted without inventing body text", async () => {
  const accepted = vi.fn(), rejected = vi.fn();
  const { result } = renderHook(() => useAgent());
  await waitFor(() => expect(result.current.currentAgent).toBe("default"));
  await act(async () => {
    await result.current.sendMessage("", undefined, [attachment], undefined, { onAccepted: accepted, onRejected: rejected });
  });
  expect(api.submitChat).toHaveBeenCalledTimes(1);
  expect(api.submitChat.mock.calls[0][1]).toBe("");
  expect(api.submitChat.mock.calls[0][4]).toEqual([attachment]);
  expect(accepted).toHaveBeenCalledOnce();
  expect(rejected).not.toHaveBeenCalled();
});

test("guiding an attachment-only queued message preserves its ID and attachments", async () => {
  const { result } = renderHook(() => useSteerQueue({
    sessionIdRef: { current: "s1" }, currentRunIdRef: { current: "r1" },
  }));
  act(() => result.current.queueFollowUp("", [attachment]));
  const id = result.current.steerMessages[0].id;
  await act(async () => { await result.current.steerMessage("", [attachment], id); });
  expect(api.steer).toHaveBeenCalledWith("s1", "", id, [attachment], "r1");
  expect(result.current.steerMessages).toHaveLength(1);
  expect(result.current.steerMessages[0]).toMatchObject({ id, queued: true, status: "pending", attachments: [attachment] });
});

test.each(["steer:message", "user:message"] as const)("attachment-only %s is rendered and acknowledged", (event) => {
  let messages: Message[] = [];
  const delivered = vi.fn();
  const ctx = {
    sessionIdRef: { current: "s1" }, processedEventIdsRef: { current: new Set<string>() },
    lastHistoryTimestampRef: { current: null }, activeSubagentStackRef: { current: [] },
    streamVersionRef: { current: 0 }, setSessionId: vi.fn(), setConnectionStatus: vi.fn(),
    setIsInitializingSandbox: vi.fn(), setSandboxError: vi.fn(),
    setActiveGoal: vi.fn(), setGoalsByRunId: vi.fn(), markSteerDelivered: delivered,
    setMessages: (update: React.SetStateAction<Message[]>) => { messages = typeof update === "function" ? update(messages) : update; },
  } as unknown as EventHandlerContext;
  handleStreamEvent({ event, data: JSON.stringify({
    content: "", message_id: "queued-image", attachments: [attachment],
  }) }, "assistant-1", "image-event", "2026-11-04T12:00:00Z", ctx);
  expect(messages.find((message) => message.id === "queued-image")).toMatchObject({
    content: "", attachments: [expect.objectContaining({ id: attachment.id, name: attachment.name })],
  });
  if (event === "steer:message") expect(delivered).toHaveBeenCalledWith("", "queued-image");
});
