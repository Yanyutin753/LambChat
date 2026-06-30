import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import test from "node:test";

const source = readFileSync(
  join(
    process.cwd(),
    "src/components/layout/AppContent/useWebSocketNotifications.tsx",
  ),
  "utf8",
);

test("task toast dismisses only itself and uses react-hot-toast visibility state", () => {
  assert.match(source, /toast\.custom\(\s*\(\s*currentToast\s*\)\s*=>/);
  assert.match(source, /currentToast\.visible/);
  assert.match(source, /toast\.dismiss\(currentToast\.id\)/);
  assert.doesNotMatch(source, /toast\.remove\(\)/);
});
