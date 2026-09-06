import { readFileSync } from "node:fs";

const oauthCallbackSource = readFileSync(
  new URL("../OAuthCallback.tsx", import.meta.url),
  "utf8",
);
const authPageSource = readFileSync(
  new URL("../AuthPage.tsx", import.meta.url),
  "utf8",
);

test("OAuth callback shows the branded auto-login splash while exchanging tokens", () => {
  expect(oauthCallbackSource).toMatch(/<AutoLoginSplash\b/);
  // 旧通用转圈退役：自动登录等待期统一走品牌过渡页
  expect(oauthCallbackSource).not.toMatch(/<Loading\b/);
});

test("auth page success-redirect state shows the branded splash", () => {
  const branchIndex = authPageSource.indexOf("if (isRedirecting) {");
  expect(branchIndex).toBeGreaterThan(-1);

  const branch = authPageSource.slice(branchIndex, branchIndex + 300);
  expect(branch).toMatch(/<AutoLoginSplash\b/);
  expect(branch).not.toMatch(/<Loading\b/);
});
