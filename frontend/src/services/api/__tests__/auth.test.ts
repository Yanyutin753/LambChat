import { buildOAuthLoginUrl } from "../auth.ts";

test("buildOAuthLoginUrl uses API base for split frontend/backend deployments", () => {
  expect(buildOAuthLoginUrl("github", "https://api.lambchat.com")).toBe(
    "https://api.lambchat.com/api/auth/oauth/github",
  );
});

test("buildOAuthLoginUrl keeps same-origin deployments relative", () => {
  expect(buildOAuthLoginUrl("google", "")).toBe("/api/auth/oauth/google");
});
