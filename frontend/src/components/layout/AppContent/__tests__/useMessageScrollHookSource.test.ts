import { readFileSync } from "node:fs";
import { resolve } from "node:path";

const hookSource = readFileSync(
  resolve(
    process.cwd(),
    "src",
    "components",
    "layout",
    "AppContent",
    "useMessageScroll.hook.ts",
  ),
  "utf8",
);

test("starts history bottom settling before browser paint", () => {
  expect(hookSource).toMatch(
    /import\s*\{[\s\S]*useRef[\s\S]*useEffect[\s\S]*useLayoutEffect[\s\S]*useState[\s\S]*useCallback[\s\S]*\}\s*from\s*"react";/,
  );
  expect(hookSource).toMatch(
    /useLayoutEffect\(\(\) => \{[\s\S]*shouldFinalizeHistoryLoadScroll[\s\S]*requestScrollToBottom\("history-finalize"/,
  );
});

test("reveals history after initial settle while recovery observation continues", () => {
  expect(hookSource).toMatch(
    /onInitialSettle:\s*\(\)\s*=>\s*\{[\s\S]*forceScrollerToPhysicalBottom[\s\S]*requestAnimationFrame\(\(\)\s*=>\s*\{[\s\S]*clearHistoryScrollSettling/,
  );
  expect(hookSource).toMatch(/onInitialSettle:[\s\S]*onComplete:\s*\(reason\)/);
});
