import { getRedirectPath, isSafeRedirectPath } from "../token.ts";

function installSessionStorage() {
  const store = new Map<string, string>();
  const original = Object.getOwnPropertyDescriptor(
    globalThis,
    "sessionStorage",
  );

  Object.defineProperty(globalThis, "sessionStorage", {
    configurable: true,
    value: {
      getItem: (key: string) => store.get(key) ?? null,
      removeItem: (key: string) => {
        store.delete(key);
      },
      setItem: (key: string, value: string) => {
        store.set(key, value);
      },
    },
  });

  return () => {
    if (original) {
      Object.defineProperty(globalThis, "sessionStorage", original);
    } else {
      delete (globalThis as { sessionStorage?: Storage }).sessionStorage;
    }
  };
}

test("auth routes are not valid post-login redirect targets", () => {
  expect(isSafeRedirectPath("/auth/callback")).toBe(false);
  expect(isSafeRedirectPath("/auth/login")).toBe(false);
  expect(isSafeRedirectPath("/")).toBe(false);
  expect(isSafeRedirectPath("/chat")).toBe(true);
  expect(isSafeRedirectPath("/chat/session-1?panel=files")).toBe(true);
});

test("getRedirectPath discards stale OAuth callback redirects", () => {
  const restore = installSessionStorage();
  try {
    sessionStorage.setItem("redirect_after_login", "/auth/callback");

    expect(getRedirectPath()).toBe(null);
    expect(sessionStorage.getItem("redirect_after_login")).toBe(null);
  } finally {
    restore();
  }
});
