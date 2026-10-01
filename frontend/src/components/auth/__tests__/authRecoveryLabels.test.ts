import { readFileSync } from "node:fs";
import { expect, test } from "vitest";

const read = (file: string) =>
  readFileSync(new URL(`../${file}`, import.meta.url), "utf8");

test("password recovery fields associate visible labels with their inputs", () => {
  const forgot = read("ForgotPassword.tsx");
  expect(forgot).toContain('htmlFor="recovery-email"');
  expect(forgot).toContain('id="recovery-email"');
  expect(forgot).toContain('autoComplete="email"');
  const reset = read("ResetPassword.tsx");
  for (const id of ["recovery-password", "recovery-confirm-password"]) {
    expect(reset).toContain(`htmlFor="${id}"`);
    expect(reset).toContain(`id="${id}"`);
  }
});

test("email verification only presents progress while a request is running", () => {
  const verify = read("VerifyEmail.tsx");
  expect(verify).toContain('{status === "loading" && t("auth.pleaseWait")}');
  expect(verify).toContain('{status === "idle" && t("auth.verifyEmailFailedDesc")}');
});
