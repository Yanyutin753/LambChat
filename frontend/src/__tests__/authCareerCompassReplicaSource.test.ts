import { readFileSync } from "node:fs";
import { resolve } from "node:path";
function readSource(path: string): string {
  return readFileSync(resolve(import.meta.dirname, path), "utf8");
}

test("login page carries the LambChat-inspired compact auth layout markers", () => {
  const authPage = readSource("../components/auth/AuthPage.tsx");
  const authStyles = readSource("../styles/auth.css");

  expect(authPage).toMatch(/auth-lamb-shell/);
  expect(authPage).toMatch(/auth-form-surface/);
  expect(authPage).toMatch(/auth\.welcomeBack/);
  expect(authPage).toMatch(/auth\.loginHint/);
  expect(authPage).toMatch(/auth-forgot-row/);
  expect(authPage).toMatch(/auth-social-provider/);
  expect(authPage).toMatch(/auth-illustration-panel/);
  expect(authPage).toMatch(/auth-character-stage/);
  expect(authPage).toMatch(/auth-mobile-spirit/);
  expect(authPage).toMatch(/handleGlobalCharacterPointerMove/);
  expect(authPage).toMatch(/window\.addEventListener\("pointermove"/);
  expect(authPage).toMatch(/auth-lamb-feature-chip/);
  expect(authPage).toMatch(/auth-character-mouth/);
  expect(authPage).not.toMatch(/auth-login-kicker/);
  expect(authPage).not.toMatch(/Agent workspace/);
  expect(authPage).toMatch(/auth-field-group/);
  expect(authPage).toMatch(/auth-submit-label/);
  expect(authPage).toMatch(/prefers-reduced-motion: reduce/);

  expect(authStyles).toMatch(/\.auth-lamb-shell/);
  expect(authStyles).toMatch(/\.auth-form-surface/);
  expect(authStyles).toMatch(/\.auth-lamb-pattern/);
  expect(authStyles).toMatch(/\.auth-forgot-row/);
  expect(authStyles).toMatch(/\.auth-social-provider/);
  expect(authStyles).toMatch(/\.auth-illustration-panel/);
  expect(authStyles).toMatch(/\.auth-character-stage/);
  expect(authStyles).toMatch(/\.auth-mobile-spirit/);
  expect(authStyles).toMatch(/background: transparent !important/);
  expect(authStyles).toMatch(/--eye-x/);
  expect(authStyles).toMatch(/--pupil-x/);
  expect(authStyles).toMatch(/--mouth-x/);
  expect(authStyles).toMatch(/--auth-accent/);
  expect(authStyles).toMatch(/--auth-character-tall/);
  expect(authStyles).toMatch(/--auth-character-glow/);
  expect(authStyles).toMatch(/--auth-character-aura/);
  expect(authStyles).toMatch(/\.auth-lamb-feature-chip/);
  expect(authStyles).not.toMatch(/\.auth-login-kicker/);
  expect(authStyles).toMatch(/\.auth-field-group/);
  expect(authStyles).toMatch(/\.auth-submit-label/);
  expect(authStyles).toMatch(/\.auth-character-antenna/);
  expect(authStyles).toMatch(/\.auth-character-cheek/);
  expect(authStyles).toMatch(/--auth-character-smile/);
  expect(authStyles).toMatch(/auth-character-blink/);
  expect(authStyles).toMatch(/\.auth-character-purple \.auth-character-mouth/);
  expect(authStyles).toMatch(/html\.dark \.auth-character-stage::before/);
  expect(authStyles).toMatch(
    /@media \(min-width: 640px\) and \(max-width: 1023px\)/,
  );
  expect(authStyles).toMatch(/@media \(max-width: 1023px\)/);
  expect(authStyles).toMatch(/@media \(max-width: 480px\)/);
});
