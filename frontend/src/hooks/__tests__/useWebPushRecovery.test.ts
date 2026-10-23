/** @vitest-environment jsdom */
import { act, renderHook, waitFor } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import { pushApi } from "../../services/api/push";
import { useWebPush } from "../useWebPush";

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

test("retired server subscription shows idle and explicit enable creates a fresh browser subscription", async () => {
  const calls: string[] = [];
  const old = {
    endpoint: "https://push/old",
    unsubscribe: vi.fn(async () => {
      calls.push("unsubscribe");
      return true;
    }),
  };
  const fresh = {
    endpoint: "https://push/fresh",
    toJSON: () => ({
      endpoint: "https://push/fresh",
      keys: { p256dh: "key", auth: "auth" },
    }),
  };
  const registration = {
    pushManager: {
      getSubscription: vi.fn(async () => old),
      subscribe: vi.fn(async () => {
        calls.push("subscribe");
        return fresh;
      }),
    },
  };
  Object.defineProperty(navigator, "serviceWorker", {
    configurable: true,
    value: {
      getRegistration: vi.fn(async () => registration),
      ready: Promise.resolve(registration),
    },
  });
  vi.stubGlobal("PushManager", class {});
  vi.stubGlobal("Notification", {
    requestPermission: vi.fn(async () => "granted"),
  });
  vi.spyOn(pushApi, "getVapidPublicKey").mockResolvedValue("AAAA");
  vi.spyOn(pushApi, "getSubscriptionStatus").mockResolvedValue({
    registered: false,
  });
  vi.spyOn(pushApi, "subscribe").mockResolvedValue({} as never);
  const { result } = renderHook(() => useWebPush());
  await waitFor(() => expect(pushApi.getSubscriptionStatus).toHaveBeenCalled());
  expect(result.current.status).toBe("idle");
  expect(old.unsubscribe).not.toHaveBeenCalled();
  await act(async () => {
    await result.current.subscribe();
  });
  expect(calls).toEqual(["unsubscribe", "subscribe"]);
  expect(pushApi.subscribe).toHaveBeenCalledWith(
    fresh.toJSON(),
    navigator.userAgent,
  );
  expect(result.current.status).toBe("subscribed");
});
