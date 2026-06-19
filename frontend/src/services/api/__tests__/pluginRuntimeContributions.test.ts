import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const source = readFileSync(
  new URL("../pluginRuntime.ts", import.meta.url),
  "utf8",
);

test("plugin runtime API consumes the extension host contribution endpoint", () => {
  assert.match(source, /const EXTENSION_HOST_API = `\$\{API_BASE\}\/api\/extensions`/);
  assert.match(source, /`\$\{EXTENSION_HOST_API\}\/contributions`/);
  assert.match(source, /`\$\{EXTENSION_HOST_API\}\/slots`/);
  assert.match(source, /`\$\{EXTENSION_HOST_API\}\/contributions\/project-options/);
  assert.match(source, /`\$\{EXTENSION_HOST_API\}\/contributions\/session-options/);
  assert.match(source, /`\$\{EXTENSION_HOST_API\}\/contributions\/channel-options/);
  assert.match(source, /`\$\{EXTENSION_HOST_API\}\/contributions\/scheduled-task-options/);
  assert.doesNotMatch(
    source,
    /`\$\{PLUGIN_RUNTIME_API\}\/contributions`/,
  );
});
