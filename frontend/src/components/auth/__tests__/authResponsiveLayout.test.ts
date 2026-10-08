import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const currentDir = dirname(fileURLToPath(import.meta.url));

function readAuthSource(fileName: string): string {
  return readFileSync(join(currentDir, fileName), "utf8");
}

test.each(["AuthPage", "AuthLayout", "ForgotPassword", "ResetPassword"])(
  "%s keeps fixed navigation below the native titlebar",
  (name) => {
    const source = readAuthSource(`../${name}.tsx`);
    const navs = source.match(/<nav\b[^>]*>/g) ?? [];
    expect(navs.length).toBeGreaterThan(0);
    for (const nav of navs) {
      expect(nav).toContain('top: "var(--titlebar-inset, 0px)"');
      expect(nav).not.toContain("fixed top-0");
    }
  },
);

test("auth pages use safe centered mobile layout classes", () => {
  const authPage = readAuthSource("../AuthPage.tsx");
  const authLayout = readAuthSource("../AuthLayout.tsx");
  const forgotPassword = readAuthSource("../ForgotPassword.tsx");
  const resetPassword = readAuthSource("../ResetPassword.tsx");

  expect(authPage.includes("max-wfull")).toBe(false);
  expect(authLayout.includes("max-wfull")).toBe(false);
  expect(forgotPassword.includes("max-wfull")).toBe(false);
  expect(resetPassword.includes("max-wfull")).toBe(false);
  expect(authPage.includes("auth-crosshatch")).toBe(true);
  // 全屏高度扣除自绘标题栏（网页 --titlebar-inset 为 0，行为不变）
  expect(
    authPage.includes("min-h-[calc(100dvh-var(--titlebar-inset,0px))]"),
  ).toBe(true);
});
