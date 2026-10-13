/** @vitest-environment jsdom */

import { afterEach, expect, test, vi } from "vitest";
import { authFetch } from "../fetch";
import { authenticatedRequest } from "../authenticatedRequest";
import { uploadApi } from "../upload";
import { refreshTokens } from "../tokenManager";
import { getAccessToken, getRefreshToken, setTokens } from "../token";

const jwt = (expires: number) => `e30.${btoa(JSON.stringify({ exp: expires }))}.signature`;
const outage = () => new Response(JSON.stringify({ detail: { code: "service_unavailable", message: "Service unavailable" } }), { status: 503 });

afterEach(() => {
  localStorage.clear();
  sessionStorage.clear();
  vi.unstubAllGlobals();
});

test("refresh dependency outage keeps status for callers and preserves tokens", async () => {
  setTokens(jwt(Date.now() / 1000 + 3600), jwt(Date.now() / 1000 + 7200));
  const before = [getAccessToken(), getRefreshToken()];
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(outage()));
  await expect(refreshTokens()).rejects.toMatchObject({ status: 503 });
  expect([getAccessToken(), getRefreshToken()]).toEqual(before);
});

for (const [name, request] of [
  ["authFetch", () => authFetch("/api/private")],
  ["authenticatedRequest", () => authenticatedRequest("/api/private")],
] as const) {
  test(`${name} does not log out when recovery refresh meets a dependency outage`, async () => {
    setTokens(jwt(Date.now() / 1000 + 3600), jwt(Date.now() / 1000 + 7200));
    const before = [getAccessToken(), getRefreshToken()];
    const logout = vi.fn();
    window.addEventListener("auth:logout", logout);
    vi.stubGlobal("fetch", vi.fn().mockResolvedValueOnce(new Response("", { status: 401 })).mockResolvedValueOnce(outage()));
    try {
      await expect(request()).rejects.toMatchObject({ status: 503 });
      expect([getAccessToken(), getRefreshToken()]).toEqual(before);
      expect(logout).not.toHaveBeenCalled();
    } finally {
      window.removeEventListener("auth:logout", logout);
    }
  });

  test(`${name} stops at unavailable proactive refresh instead of sending an unauthenticated request`, async () => {
    setTokens(jwt(Date.now() / 1000 - 100), jwt(Date.now() / 1000 + 7200));
    const before = [getAccessToken(), getRefreshToken()];
    const fetchMock = vi.fn().mockResolvedValue(outage());
    vi.stubGlobal("fetch", fetchMock);
    await expect(request()).rejects.toMatchObject({ status: 503 });
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect([getAccessToken(), getRefreshToken()]).toEqual(before);
  });
}

for (const [name, request] of [
  ["authFetch", () => authFetch("/api/private")],
  ["authenticatedRequest", () => authenticatedRequest("/api/private")],
] as const) {
  test(`${name} still clears credentials when refresh genuinely rejects authentication`, async () => {
    setTokens(jwt(Date.now() / 1000 + 3600), jwt(Date.now() / 1000 + 7200));
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response("", { status: 401 })));
    await expect(request()).rejects.toThrow();
    expect(getAccessToken()).toBeNull();
    expect(getRefreshToken()).toBeNull();
  });
}


test("upload rejects unavailable proactive refresh without sending anonymously or hanging", async () => {
  setTokens(jwt(Date.now() / 1000 - 100), jwt(Date.now() / 1000 + 7200));
  const before = [getAccessToken(), getRefreshToken()];
  const send = vi.fn();
  vi.stubGlobal("XMLHttpRequest", class { send = send; });
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(outage()));
  await expect(uploadApi.uploadFile(new File(["owned"], "owned.txt")).promise).rejects.toMatchObject({ status: 503 });
  expect(send).not.toHaveBeenCalled();
  expect([getAccessToken(), getRefreshToken()]).toEqual(before);
});

for (const [name, request] of [
  ["authFetch", () => authFetch("/api/private")],
  ["authenticatedRequest", () => authenticatedRequest("/api/private")],
] as const) {
  test(`${name} clears a rejected access token when no refresh token remains`, async () => {
    setTokens(jwt(Date.now() / 1000 + 3600));
    expect(getRefreshToken()).toBeNull();
    const logout = vi.fn();
    window.addEventListener("auth:logout", logout);
    const fetchMock = vi.fn().mockResolvedValue(new Response("", { status: 401 }));
    vi.stubGlobal("fetch", fetchMock);
    try {
      await expect(request()).rejects.toThrow();
      expect(getAccessToken()).toBeNull();
      expect(getRefreshToken()).toBeNull();
      expect(logout).toHaveBeenCalledOnce();
      expect(fetchMock).toHaveBeenCalledTimes(1);
    } finally {
      window.removeEventListener("auth:logout", logout);
    }
  });
}
