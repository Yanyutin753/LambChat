import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const currentDir = dirname(fileURLToPath(import.meta.url));
const welcomePageSource = readFileSync(
  resolve(currentDir, "../WelcomePage.tsx"),
  "utf8",
);
const animatedWebp = readFileSync(
  resolve(currentDir, "../../../../public/images/lamb.webp"),
);

test("embeds the transparent animated welcome icon WebP as the welcome icon image", () => {
  expect(welcomePageSource).toMatch(/WELCOME_ICON_SRC/);
  expect(welcomePageSource).toMatch(/\/images\/lamb\.webp/);
  expect(welcomePageSource).toMatch(/src=\{WELCOME_ICON_SRC\}/);
  expect(welcomePageSource).not.toMatch(
    /<img[\s\S]*src="\/icons\/icon\.svg"[\s\S]*className="welcome-icon/,
  );
  expect(welcomePageSource).not.toMatch(/<video/);
  expect(animatedWebp.toString("latin1")).toMatch(/ANMF/);
  expect(
    (animatedWebp.toString("latin1").match(/ANMF/g)?.length ?? 0) >= 50,
  ).toBeTruthy();
  expect(welcomePageSource).not.toMatch(
    /<img[\s\S]*className="welcome-icon[\s\S]*rounded-full/,
  );
});
