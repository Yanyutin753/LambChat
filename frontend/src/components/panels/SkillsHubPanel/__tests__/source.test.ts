import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";

const __dirname = dirname(fileURLToPath(import.meta.url));

test("plugin runtime tab is not blocked by the global skills feature switch", () => {
  const source = readFileSync(resolve(__dirname, "../..", "SkillsHubPanel.tsx"), "utf8");

  assert.match(source, /!enableSkills\s*&&\s*visibleTab\s*!==\s*"plugins"/);
});
