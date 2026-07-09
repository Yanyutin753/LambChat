import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const currentDir = dirname(fileURLToPath(import.meta.url));

function readAuthSource(fileName: string): string {
  return readFileSync(join(currentDir, fileName), "utf8");
}

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
  expect(authPage.includes("min-h-[100dvh]")).toBe(true);
});
