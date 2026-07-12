import { existsSync, readFileSync } from "node:fs";

test("App uses ChatPageSkeleton for the top-level route suspense fallback", () => {
  const appSource = readFileSync(
    new URL("../../../App.tsx", import.meta.url),
    "utf8",
  );

  expect(appSource).toMatch(
    /import\s+\{[^}]*ChatPageSkeleton[^}]*\}\s+from\s+"\.\/components\/skeletons";/,
  );
  expect(appSource).toMatch(/<Suspense fallback=\{<ChatPageSkeleton \/>\}>/);
  expect(appSource).not.toMatch(/RouteLoadingShell/);
});

test("legacy route loading shell component is removed", () => {
  expect(existsSync(new URL("./RouteLoadingShell.ts", import.meta.url))).toBe(
    false,
  );
});
