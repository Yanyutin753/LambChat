import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const currentDir = dirname(fileURLToPath(import.meta.url));
const i18nSource = readFileSync(resolve(currentDir, "../index.ts"), "utf8");

test("i18next support notice is disabled for application startup", () => {
  expect(i18nSource).toMatch(/showSupportNotice:\s*false/);
});
