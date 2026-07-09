import { readFileSync } from "node:fs";
import { join } from "node:path";
const source = readFileSync(
  join(
    process.cwd(),
    "src/components/layout/AppContent/useWebSocketNotifications.tsx",
  ),
  "utf8",
);

test("task toast dismisses only itself and uses react-hot-toast visibility state", () => {
  expect(source).toMatch(/toast\.custom\(\s*\(\s*currentToast\s*\)\s*=>/);
  expect(source).toMatch(/currentToast\.visible/);
  expect(source).toMatch(/toast\.dismiss\(currentToast\.id\)/);
  expect(source).not.toMatch(/toast\.remove\(\)/);
});
