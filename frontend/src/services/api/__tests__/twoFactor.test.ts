/** @vitest-environment jsdom */
import { afterEach, expect, test, vi } from "vitest";
import { authApi, TwoFactorRequiredError } from "../auth";
import { getAccessToken, setTokens } from "../token";

const { request } = vi.hoisted(() => ({ request: vi.fn() }));
vi.mock("../fetch", () => ({ authFetch: request }));
afterEach(() => {
  localStorage.clear();
  vi.resetAllMocks();
});

test("a primary sign-in challenge is never stored as an access token", async () => {
  request.mockResolvedValue({
    two_factor_required: true,
    challenge_token: "opaque",
  });
  await expect(
    authApi.login({ username: "a", password: "secret" }),
  ).rejects.toBeInstanceOf(TwoFactorRequiredError);
  expect(getAccessToken()).toBeNull();
});

test("an OAuth JSON challenge also requires the second factor", async () => {
  request.mockResolvedValue({
    two_factor_required: true,
    challenge_token: "opaque",
  });
  await expect(
    authApi.handleOAuthCallback("github", "code", "state"),
  ).rejects.toBeInstanceOf(TwoFactorRequiredError);
  expect(getAccessToken()).toBeNull();
});

test("a late security response cannot replace another account's tokens", async () => {
  const token = (sub: string) =>
    `e30.${btoa(JSON.stringify({ sub }))}.signature`;
  setTokens(token("original"), "refresh-original");
  request.mockImplementation(async () => {
    setTokens(token("new-account"), "refresh-new");
    return {
      access_token: token("original"),
      refresh_token: "rotated",
      recovery_codes: [],
    };
  });
  await expect(
    authApi.updateTwoFactor("disable", "password", "123456"),
  ).rejects.toThrow();
  expect(getAccessToken()).toBe(token("new-account"));
});
