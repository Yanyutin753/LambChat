/** @vitest-environment jsdom */
import { act, cleanup, renderHook } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import { SESSIONS_READ_INVALIDATED_EVENT } from "../../../../services/api/session";

const mocks = vi.hoisted(() => ({ user: { id: "old" } }));
vi.mock("../../../../hooks/useAuth", () => ({
  useAuth: () => ({ user: mocks.user }),
}));
vi.mock("../../../../services/api/tokenManager", () => ({
  getValidAccessToken: async () => `token-${mocks.user.id}`,
  refreshAccessToken: vi.fn(),
}));
vi.mock("../../../../services/api", () => ({ getRefreshToken: () => null }));
vi.mock("../taskCompletionJournal", () => ({
  useTaskCompletionJournal: () => async () => {},
}));
vi.mock("../../../../hooks/useBrowserNotification", () => ({
  useBrowserNotification: () => ({
    notify: vi.fn(),
    isSupported: false,
    permission: "denied",
  }),
}));
vi.mock("react-router-dom", () => ({ useNavigate: () => vi.fn() }));
import { useWebSocketNotifications } from "../useWebSocketNotifications";

class Socket {
  static OPEN = 1;
  static CONNECTING = 0;
  static instances: Socket[] = [];
  readyState = 1;
  onopen: (() => void) | null = null;
  onmessage: ((event: { data: string }) => void) | null = null;
  onclose: ((event: { code: number; reason: string }) => void) | null = null;
  onerror: (() => void) | null = null;
  send = vi.fn();
  constructor() {
    Socket.instances.push(this);
  }
  close() {
    this.readyState = 3;
    this.onclose?.({ code: 1000, reason: "" });
  }
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

test("an old authenticated socket cannot mark the next account's sessions read", async () => {
  mocks.user = { id: "old" };
  Socket.instances = [];
  vi.stubGlobal("WebSocket", Socket);
  const reads: unknown[] = [];
  const onRead = (event: Event) => reads.push((event as CustomEvent).detail);
  window.addEventListener(SESSIONS_READ_INVALIDATED_EVENT, onRead);
  try {
    const hook = renderHook(() =>
      useWebSocketNotifications({ sessionId: "current", enabled: true }),
    );
    await act(async () => {});
    const oldSocket = Socket.instances[0];
    const oldMessage = oldSocket.onmessage!;
    act(() =>
      oldMessage({
        data: JSON.stringify({
          type: "sessions:read",
          data: { session_id: "old-session" },
        }),
      }),
    );
    expect(reads).toEqual([{ sessionId: "old-session" }]);
    reads.length = 0;

    mocks.user = { id: "new" };
    hook.rerender();
    await act(async () => {});
    act(() =>
      oldMessage({
        data: JSON.stringify({ type: "sessions:read", data: {} }),
      }),
    );

    expect(reads).toEqual([]);
    const newSocket = Socket.instances[1];
    act(() =>
      newSocket.onmessage!({
        data: JSON.stringify({
          type: "sessions:read",
          data: { session_id: "new-session" },
        }),
      }),
    );
    expect(reads).toEqual([{ sessionId: "new-session" }]);
  } finally {
    window.removeEventListener(SESSIONS_READ_INVALIDATED_EVENT, onRead);
  }
});
