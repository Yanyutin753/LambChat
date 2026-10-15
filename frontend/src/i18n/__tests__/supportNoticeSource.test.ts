import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const currentDir = dirname(fileURLToPath(import.meta.url));
const i18nSource = readFileSync(resolve(currentDir, "../index.ts"), "utf8");

test("i18next initialization omits the removed support-notice option", () => {
  expect(i18nSource).not.toContain("showSupportNotice");
});
