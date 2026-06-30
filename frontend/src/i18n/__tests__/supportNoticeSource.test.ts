import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const currentDir = dirname(fileURLToPath(import.meta.url));
const i18nSource = readFileSync(resolve(currentDir, "../index.ts"), "utf8");

test("i18next support notice is disabled for application startup", () => {
  assert.match(i18nSource, /showSupportNotice:\s*false/);
});
