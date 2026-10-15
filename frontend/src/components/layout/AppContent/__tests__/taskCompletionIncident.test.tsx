/** @vitest-environment jsdom */
import { act, cleanup, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import type { TaskCompletionEvent } from "../../../../services/api/taskCompletions";

const mocks = vi.hoisted(() => ({
  user: { id: "incident-catchup" },
  get: vi.fn(),
  events: vi.fn(),
  journal: vi.fn(),
  toast: vi.fn(),
  remove: vi.fn(),
  dismiss: vi.fn(),
  navigate: vi.fn(),
}));
vi.mock("../../../../hooks/useAuth", () => ({
  useAuth: () => ({ user: mocks.user }),
}));
vi.mock("../../../../hooks/useWebSocket", () => ({ useWebSocket: vi.fn() }));
vi.mock("../../../../hooks/useBrowserNotification", () => ({
  useBrowserNotification: () => ({
    notify: vi.fn(),
    isSupported: false,
    permission: "denied",
  }),
}));
vi.mock("react-router-dom", () => ({ useNavigate: () => mocks.navigate }));
vi.mock("react-hot-toast", () => ({
  toast: { custom: mocks.toast, remove: mocks.remove, dismiss: mocks.dismiss },
}));
vi.mock("../../../../services/api", () => ({
  sessionApi: { get: mocks.get, getEvents: mocks.events },
}));
vi.mock("../../../../services/api/taskCompletions", () => ({
  getTaskCompletions: mocks.journal,
}));
vi.mock("../../../../services/notifications/appNotificationService", () => ({
  appNotificationService: { getRuntime: () => "unsupported" },
}));
import { useWebSocketNotifications } from "../useWebSocketNotifications";

beforeEach(() => {
  vi.resetAllMocks();
  localStorage.clear();
  sessionStorage.clear();
  mocks.user = { id: "incident-catchup" };
  mocks.toast.mockReturnValue("incident-toast");
});
afterEach(() => {
  cleanup();
  vi.useRealTimers();
});

function completion(id: string, createdAt: string): TaskCompletionEvent {
  return {
    id,
    session_id: `${id}-session`,
    run_id: `${id}-run`,
    status: "completed",
    created_at: createdAt,
    dedupe_key: `incident:${id}`,
    notification_kind: "run_complete",
  };
}

const cursorKey = (userId: string) =>
  `lambchat.taskCompletions.cursor.${userId}`;

test("176 pre-login completions for 140 expired sessions advance every page without history reads, then a fresh completion delivers its metadata and history", async () => {
  const oldTime = new Date(Date.now() - 60_000).toISOString();
  const oldEvents = Array.from({ length: 176 }, (_, index) => ({
    ...completion(`old-${index}`, oldTime),
    session_id: `expired-${index % 140}`,
    status: index < 165 ? "completed" : "cancelled",
  }));
  expect(new Set(oldEvents.map((event) => event.session_id)).size).toBe(140);
  mocks.journal.mockImplementation(async (cursor: string | null) => {
    const offset = cursor ? Number(cursor.slice("old-".length)) : 0;
    const end = Math.min(offset + 50, oldEvents.length);
    return {
      items: oldEvents.slice(offset, end),
      cursor: `old-${end}`,
      next_cursor: end < oldEvents.length ? `old-${end}` : null,
    };
  });
  const onSessionUnread = vi.fn();
  renderHook(() =>
    useWebSocketNotifications({
      sessionId: "currently-open",
      onSessionUnread,
    }),
  );
  await act(async () => {});

  expect(mocks.journal.mock.calls.map(([cursor]) => cursor)).toEqual([
    null,
    "old-50",
    "old-100",
    "old-150",
  ]);
  const since = mocks.journal.mock.calls[0][1] as string;
  expect(Date.parse(since)).toBeGreaterThan(Date.parse(oldTime));
  expect(mocks.journal.mock.calls.every(([, value]) => value === since)).toBe(
    true,
  );
  expect(localStorage.getItem(cursorKey(mocks.user.id))).toBe("old-176");
  expect(mocks.get).not.toHaveBeenCalled();
  expect(mocks.events).not.toHaveBeenCalled();
  expect(mocks.toast).not.toHaveBeenCalled();
  expect(onSessionUnread).not.toHaveBeenCalled();

  const freshTime = new Date(Date.parse(since) + 1_000).toISOString();
  const fresh = {
    ...completion("fresh", freshTime),
    project_id: "fresh-project",
    scheduled_task_id: "fresh-schedule",
    is_favorite: true,
    unread_count: 2,
  };
  const history = {
    events: [
      {
        event_type: "user:message",
        run_id: fresh.run_id,
        timestamp: freshTime,
        data: {
          content: "Inspect the full result",
          attachments: [{ name: "input.txt" }],
        },
      },
      {
        event_type: "tool:start",
        run_id: fresh.run_id,
        timestamp: freshTime,
        data: {
          tool: "read_file",
          tool_call_id: "fresh-tool",
          args: { path: "input.txt" },
        },
      },
      {
        event_type: "tool:result",
        run_id: fresh.run_id,
        timestamp: freshTime,
        data: {
          tool: "read_file",
          tool_call_id: "fresh-tool",
          success: true,
          result: "source content",
        },
      },
      {
        event_type: "message:chunk",
        run_id: fresh.run_id,
        timestamp: freshTime,
        data: { content: "The complete fresh result remains available." },
      },
    ],
  };
  const originalHistory = structuredClone(history);
  mocks.get.mockResolvedValue({
    session_id: fresh.session_id,
    name: "Fresh task metadata",
    unread_count: 2,
    last_read_at: oldTime,
    metadata: { project_id: fresh.project_id },
  });
  mocks.events.mockResolvedValue(history);
  mocks.journal.mockResolvedValue({
    items: [fresh],
    cursor: "fresh-cursor",
    next_cursor: null,
  });
  await act(async () => {
    window.dispatchEvent(new Event("online"));
  });

  expect(mocks.journal).toHaveBeenLastCalledWith("old-176", since);
  expect(mocks.get).toHaveBeenCalledExactlyOnceWith(fresh.session_id);
  expect(mocks.events).toHaveBeenCalledExactlyOnceWith(fresh.session_id, {
    run_id: fresh.run_id,
  });
  expect(history).toEqual(originalHistory);
  expect(onSessionUnread).toHaveBeenCalledExactlyOnceWith(
    fresh.session_id,
    2,
    fresh.project_id,
    true,
    fresh.scheduled_task_id,
  );
  expect(mocks.toast).toHaveBeenCalledOnce();
  const notification = mocks.toast.mock.calls[0][0]({
    id: "incident-toast",
    visible: true,
  });
  expect(notification.props.title).toBe("Fresh task metadata");
  expect(notification.props.body).toBe(
    "The complete fresh result remains available.",
  );
  act(() => notification.props.onOpen());
  expect(mocks.navigate).toHaveBeenCalledWith(
    "/chat/fresh-session?run_id=fresh-run",
    {
      replace: true,
      state: { externalNavigate: true, scrollToBottom: true },
    },
  );
  expect(localStorage.getItem(cursorKey(mocks.user.id))).toBe("fresh-cursor");
});

test("a new completion whose session genuinely returns 404 advances the cursor without a toast or retry loop", async () => {
  vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout"] });
  mocks.user = { id: "incident-new-deleted" };
  const missing = completion(
    "new-deleted",
    new Date(Date.now() + 1_000).toISOString(),
  );
  const notFound = Object.assign(new Error("Session not found"), {
    status: 404,
  });
  mocks.get.mockRejectedValue(notFound);
  mocks.events.mockRejectedValue(notFound);
  mocks.journal.mockResolvedValue({
    items: [missing],
    cursor: "after-deleted",
    next_cursor: null,
  });
  const onSessionUnread = vi.fn();
  renderHook(() =>
    useWebSocketNotifications({ sessionId: "currently-open", onSessionUnread }),
  );
  await act(async () => {});

  expect(mocks.get).toHaveBeenCalledExactlyOnceWith(missing.session_id);
  expect(mocks.events).toHaveBeenCalledExactlyOnceWith(missing.session_id, {
    run_id: missing.run_id,
  });
  expect(localStorage.getItem(cursorKey(mocks.user.id))).toBe("after-deleted");
  expect(mocks.toast).not.toHaveBeenCalled();
  expect(mocks.navigate).not.toHaveBeenCalled();
  expect(onSessionUnread).not.toHaveBeenCalled();
  await act(async () => {
    await vi.advanceTimersByTimeAsync(60_000);
  });
  expect(mocks.journal).toHaveBeenCalledOnce();
  expect(mocks.get).toHaveBeenCalledOnce();
  expect(mocks.events).toHaveBeenCalledOnce();

  const since = mocks.journal.mock.calls[0][1];
  mocks.journal.mockResolvedValue({
    items: [],
    cursor: "after-deleted",
    next_cursor: null,
  });
  await act(async () => {
    window.dispatchEvent(new Event("online"));
  });
  expect(mocks.journal).toHaveBeenLastCalledWith("after-deleted", since);
  expect(mocks.get).toHaveBeenCalledOnce();
  expect(mocks.events).toHaveBeenCalledOnce();
  expect(mocks.toast).not.toHaveBeenCalled();
});
