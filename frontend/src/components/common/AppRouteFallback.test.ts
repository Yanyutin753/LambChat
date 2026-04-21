import assert from "node:assert/strict";
import test from "node:test";
import { existsSync, readFileSync } from "node:fs";

test("App uses ChatPageSkeleton for the top-level route suspense fallback", () => {
  const appSource = readFileSync(
    new URL("../../App.tsx", import.meta.url),
    "utf8",
  );

  assert.match(
    appSource,
    /import\s+\{[^}]*ChatPageSkeleton[^}]*\}\s+from\s+"\.\/components\/skeletons";/,
  );
  assert.match(appSource, /<Suspense fallback=\{<ChatPageSkeleton \/>\}>/);
  assert.doesNotMatch(appSource, /RouteLoadingShell/);
});

test("legacy route loading shell component is removed", () => {
  assert.equal(
    existsSync(new URL("./RouteLoadingShell.ts", import.meta.url)),
    false,
  );
});
