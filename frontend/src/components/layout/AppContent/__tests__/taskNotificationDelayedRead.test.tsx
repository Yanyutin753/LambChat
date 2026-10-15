/** @vitest-environment jsdom */
import { useRef, useState } from "react";
import { act, cleanup, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import type { BackendSession } from "../../../../services/api/session";
import type { UnreadBySession } from "../../../sidebar/unreadCounts";

const mocks = vi.hoisted(() => ({
  handlers: {} as {
    onTaskComplete?: (event: unknown) => void;
    onSessionsRead?: (scope: object) => void;
  },
  get: vi.fn(),
  visibleToasts: new Set<string>(),
}));
vi.mock("../../../../hooks/useAuth", () => ({
  useAuth: () => ({ user: { id: "delayed-read-owner" } }),
}));
vi.mock("../../../../hooks/useWebSocket", () => ({
  useWebSocket: (handlers: typeof mocks.handlers) => {
    mocks.handlers = handlers;
  },
}));
vi.mock("../../../../hooks/useBrowserNotification", () => ({
  useBrowserNotification: () => ({
    notify: vi.fn(),
    isSupported: false,
    permission: "denied",
  }),
}));
vi.mock("react-router-dom", () => ({ useNavigate: () => vi.fn() }));
vi.mock("react-hot-toast", () => ({
  default: { error: vi.fn(), success: vi.fn() },
  toast: {
    custom: () => {
      mocks.visibleToasts.add("new-completion-toast");
      return "new-completion-toast";
    },
    remove: (id: string) => mocks.visibleToasts.delete(id),
    dismiss: (id: string) => mocks.visibleToasts.delete(id),
  },
}));
vi.mock("../../../../services/api", () => ({
  sessionApi: { get: mocks.get, getEvents: async () => ({ events: [] }) },
}));
vi.mock("../../../../services/api/taskCompletions", () => ({
  getTaskCompletions: async () => ({
    items: [],
    cursor: null,
    next_cursor: null,
  }),
}));
vi.mock("../../../../services/notifications/appNotificationService", () => ({
  appNotificationService: { getRuntime: () => "unsupported" },
}));
import { useSessionSidebarActions } from "../../../../hooks/useSessionSidebarActions";
import { useWebSocketNotifications } from "../useWebSocketNotifications";

const newerSession: BackendSession = {
  id: "delayed-read-session",
  user_id: "delayed-read-owner",
  agent_id: "fast",
  created_at: "2026-10-15T00:00:00Z",
  updated_at: "2026-10-15T00:02:00Z",
  last_read_at: "2026-10-15T00:01:00Z",
  is_active: true,
  name: "New completed task",
  metadata: { task_status: "completed" },
  unread_count: 1,
};

beforeEach(() => {
  vi.clearAllMocks();
  mocks.visibleToasts.clear();
  mocks.get.mockResolvedValue(newerSession);
});
afterEach(cleanup);

function useSidebarAndNotifications() {
  const [sessions, setSessions] = useState([newerSession]);
  const [unread, setUnread] = useState<UnreadBySession>(new Map());
  const projectRefs = useRef(new Map());
  const scheduledTaskRefs = useRef(new Map());
  const actions = useSessionSidebarActions({
    unreadBySession: unread,
    uncategorizedList: {
      sessions,
      updateSession: (session) => setSessions([session]),
      removeSession: () => {},
      prependSession: () => {},
      softRefresh: () => setSessions([newerSession]),
      refresh: async () => setSessions([newerSession]),
    },
    projectRefs,
    scheduledTaskRefs,
    projects: [],
    currentSessionId: "other-session",
    setUnreadBySession: setUnread,
    onNewSession: () => {},
    onSelectSession: () => {},
    getProjectRef: () => null,
  });
  useWebSocketNotifications({
    sessionId: "other-session",
    onSessionUnread: actions.handleSessionUnread,
  });
  return { sessions, unread, updateUnread: actions.handleSessionUnread };
}

function emitCompletion(run: string, status = "completed") {
  mocks.handlers.onTaskComplete?.({
    data: {
      session_id: newerSession.id,
      run_id: run,
      status,
      created_at: "2026-10-15T00:02:00Z",
      unread_count: newerSession.unread_count,
    },
  });
}

test("a delayed remote read preserves a completion newer than the persisted read", async () => {
  const hook = renderHook(useSidebarAndNotifications);
  await act(async () => {
    emitCompletion("run-after-read");
  });
  expect(mocks.visibleToasts.has("new-completion-toast")).toBe(true);
  expect(hook.result.current.sessions[0].unread_count).toBe(1);

  // Replica A's mark-read completed before replica B wrote the new completion,
  // but its scope-only websocket broadcast reaches this browser last.
  await act(async () => {
    mocks.handlers.onSessionsRead?.({ sessionId: newerSession.id });
  });

  expect(hook.result.current.sessions[0].unread_count).toBe(1);
  expect(mocks.visibleToasts.has("new-completion-toast")).toBe(true);
});

test("a remote read removes a task actually covered by the persisted read", async () => {
  const hook = renderHook(useSidebarAndNotifications);
  await act(async () => emitCompletion("run-read-later"));
  expect(mocks.visibleToasts.has("new-completion-toast")).toBe(true);
  mocks.get.mockResolvedValue({
    ...newerSession,
    unread_count: 0,
    last_read_at: "2026-10-15T00:03:00Z",
  });
  await act(
    async () => mocks.handlers.onSessionsRead?.({ sessionId: newerSession.id }),
  );
  expect(hook.result.current.sessions[0].unread_count).toBe(0);
  expect(mocks.visibleToasts.has("new-completion-toast")).toBe(false);
});

test("an old remote read cannot suppress a newer completion whose lookup is pending", async () => {
  let resolve!: (session: BackendSession) => void;
  mocks.get.mockImplementationOnce(
    () =>
      new Promise<BackendSession>((done) => {
        resolve = done;
      }),
  );
  const hook = renderHook(useSidebarAndNotifications);
  act(() => emitCompletion("pending-new-completion"));
  await act(
    async () => mocks.handlers.onSessionsRead?.({ sessionId: newerSession.id }),
  );
  await act(async () => resolve(newerSession));
  expect(hook.result.current.sessions[0].unread_count).toBe(1);
  expect(mocks.visibleToasts.has("new-completion-toast")).toBe(true);
});

test("a delayed remote read keeps a newer human confirmation despite zero unread replies", async () => {
  mocks.get.mockResolvedValue({ ...newerSession, unread_count: 0 });
  renderHook(useSidebarAndNotifications);
  await act(async () =>
    emitCompletion("new-human-confirmation", "waiting_human"),
  );
  expect(mocks.visibleToasts.has("new-completion-toast")).toBe(true);
  await act(
    async () => mocks.handlers.onSessionsRead?.({ sessionId: newerSession.id }),
  );
  expect(mocks.visibleToasts.has("new-completion-toast")).toBe(true);
});

test("a read snapshot cannot overwrite a completion received while its lookup is pending", async () => {
  let resolve!: (session: BackendSession) => void;
  mocks.get.mockImplementationOnce(
    () =>
      new Promise<BackendSession>((done) => {
        resolve = done;
      }),
  );
  const hook = renderHook(useSidebarAndNotifications);
  act(() => mocks.handlers.onSessionsRead?.({ sessionId: newerSession.id }));
  act(() => hook.result.current.updateUnread(newerSession.id, 2));
  await act(async () => resolve({ ...newerSession, unread_count: 0 }));
  expect(hook.result.current.sessions[0].unread_count).toBe(2);
});
