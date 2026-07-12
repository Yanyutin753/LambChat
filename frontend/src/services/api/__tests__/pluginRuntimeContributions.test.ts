import { readFileSync } from "node:fs";
const source = readFileSync(
  new URL("../pluginRuntime.ts", import.meta.url),
  "utf8",
);

test("plugin runtime API consumes the extension host contribution endpoint", () => {
  expect(source).toMatch(/const EXTENSION_HOST_API = `\$\{API_BASE\}\/api\/extensions`/);
  expect(source).toMatch(/`\$\{EXTENSION_HOST_API\}\/contributions`/);
  expect(source).toMatch(/`\$\{EXTENSION_HOST_API\}\/slots`/);
  expect(source).toMatch(/`\$\{EXTENSION_HOST_API\}\/contributions\/project-options/);
  expect(source).toMatch(/`\$\{EXTENSION_HOST_API\}\/contributions\/session-options/);
  expect(source).toMatch(/`\$\{EXTENSION_HOST_API\}\/contributions\/channel-options/);
  expect(source).toMatch(/`\$\{EXTENSION_HOST_API\}\/contributions\/scheduled-task-options/);
  expect(source).not.toMatch(/`\$\{PLUGIN_RUNTIME_API\}\/contributions`/);
});
