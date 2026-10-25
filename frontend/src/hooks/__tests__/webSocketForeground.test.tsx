/** @vitest-environment jsdom */
import { act, cleanup, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
const mocks = vi.hoisted(() => ({
  token: vi.fn(),
  refresh: vi.fn(),
  refreshToken: vi.fn(),
}));
vi.mock("../../services/api/tokenManager", () => ({
  getValidAccessToken: mocks.token,
  refreshAccessToken: mocks.refresh,
}));
vi.mock("../../services/api", () => ({ getRefreshToken: mocks.refreshToken }));
import { useWebSocket } from "../useWebSocket";
class Socket {
  static OPEN = 1;
  static CONNECTING = 0;
  static instances: Socket[] = [];
  readyState = Socket.OPEN;
  onopen: (() => void) | null = null;
  onmessage: ((event: { data: string }) => void) | null = null;
  onclose: ((event: { code: number; reason: string }) => void) | null = null;
  onerror: (() => void) | null = null;
  send = vi.fn();
  close = vi.fn(() => {
    this.readyState = 3;
    this.onclose?.({ code: 1000, reason: "" });
  });
  constructor() {
    Socket.instances.push(this);
  }
}
beforeEach(() => {
  vi.useFakeTimers();
  Socket.instances = [];
  mocks.token.mockReset().mockResolvedValue("token");
  mocks.refresh.mockReset();
  mocks.refreshToken.mockReset().mockReturnValue(null);
  vi.stubGlobal("WebSocket", Socket);
});
afterEach(() => {
  cleanup();
  vi.useRealTimers();
  vi.unstubAllGlobals();
});
test("resume replaces a silent open socket and ignores its late notifications", async () => {
  const notify = vi.fn();
  renderHook(() => useWebSocket({ userId: "owner", onTaskComplete: notify }));
  await act(async () => {});
  const old = Socket.instances[0];
  const late = old.onmessage!;
  await act(async () => document.dispatchEvent(new Event("resume")));
  expect(old.close).toHaveBeenCalledOnce();
  expect(Socket.instances).toHaveLength(2);
  act(() =>
    late({
      data: JSON.stringify({
        type: "task:complete",
        data: { session_id: "old" },
      }),
    }),
  );
  expect(notify).not.toHaveBeenCalled();
});
test("resume invalidates connection setup that never finished before suspension", async () => {
  let finish!: (token: string) => void;
  mocks.token.mockReturnValueOnce(
    new Promise((resolve) => {
      finish = resolve;
    }),
  );
  renderHook(() => useWebSocket({ userId: "owner" }));
  await act(async () => {});
  await act(async () => document.dispatchEvent(new Event("resume")));
  expect(Socket.instances).toHaveLength(1);
  await act(async () => finish("old-token"));
  expect(Socket.instances).toHaveLength(1);
});

test("visibility recovers both sockets that look open and those stuck connecting", async () => {
  renderHook(() => useWebSocket({ userId: "owner" }));
  await act(async () => {});
  const old = Socket.instances[0];
  old.readyState = Socket.CONNECTING;
  const visibility = vi.spyOn(document, "visibilityState", "get");
  try {
    visibility.mockReturnValue("hidden");
    act(() => document.dispatchEvent(new Event("visibilitychange")));
    visibility.mockReturnValue("visible");
    await act(async () => {
      document.dispatchEvent(new Event("visibilitychange"));
      document.dispatchEvent(new Event("resume"));
      window.dispatchEvent(new Event("online"));
    });
    expect(old.close).toHaveBeenCalledOnce();
    expect(Socket.instances).toHaveLength(2);
  } finally {
    visibility.mockRestore();
  }
});
test("disabled or unmounted sockets cannot be restarted by resume", async () => {
  const hook = renderHook(() =>
    useWebSocket({ userId: "owner", enabled: false }),
  );
  await act(async () => document.dispatchEvent(new Event("resume")));
  expect(Socket.instances).toHaveLength(0);
  hook.unmount();
  await act(async () => document.dispatchEvent(new Event("resume")));
  expect(Socket.instances).toHaveLength(0);
});

test("a transient token refresh failure retries without another resume event", async () => {
  mocks.token.mockRejectedValueOnce(new DOMException("Aborted", "AbortError"));
  renderHook(() => useWebSocket({ userId: "owner" }));
  await act(async () => {});
  expect(Socket.instances).toHaveLength(0);
  await act(async () => {
    await vi.advanceTimersByTimeAsync(1000);
  });
  expect(Socket.instances).toHaveLength(1);
});

test("authentication reconnect recovers when refresh briefly fails after a close", async () => {
  mocks.refreshToken.mockReturnValue("refresh-token");
  mocks.refresh.mockRejectedValueOnce(new Error("network unavailable"));
  renderHook(() => useWebSocket({ userId: "owner" }));
  await act(async () => {});
  const old = Socket.instances[0];
  await act(async () => old.onclose?.({ code: 4001, reason: "Unauthorized" }));
  await act(async () => {
    await vi.advanceTimersByTimeAsync(1000);
  });
  expect(Socket.instances).toHaveLength(2);
});
