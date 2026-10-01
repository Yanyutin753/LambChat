import { readFileSync } from "node:fs";

const welcomePageSource = readFileSync(
  new URL("../WelcomePage.tsx", import.meta.url),
  "utf8",
);
const welcomeStyles = readFileSync(
  new URL("../../../styles/welcome.css", import.meta.url),
  "utf8",
);

test("welcome artwork restores the original animation with a reduced-motion fallback", () => {
  expect(welcomePageSource).toContain('src="/images/lamb.webp"');
  expect(welcomePageSource).toContain(
    'media="(prefers-reduced-motion: reduce)"',
  );
  expect(welcomePageSource).toContain(
    'srcSet="/images/illustrations/lamb-welcome.png"',
  );
  expect(welcomePageSource).not.toMatch(/<video/);
  expect(welcomePageSource).not.toMatch(/welcome-icon[^"\n]*rounded-full/);
  expect(welcomeStyles).not.toMatch(/welcome-icon-pulse/);
});
