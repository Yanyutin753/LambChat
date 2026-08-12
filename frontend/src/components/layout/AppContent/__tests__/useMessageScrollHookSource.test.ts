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

test("positions accepted history once before browser paint", () => {
  expect(hookSource).toMatch(
    /import\s*\{[\s\S]*useRef[\s\S]*useEffect[\s\S]*useLayoutEffect[\s\S]*useState[\s\S]*useCallback[\s\S]*\}\s*from\s*"react";/,
  );
  expect(hookSource).toMatch(
    /useLayoutEffect\(\(\) => \{[\s\S]*shouldFinalizeHistoryLoadScroll[\s\S]*const virtuoso = virtuosoRef\.current;[\s\S]*virtuoso\.scrollToIndex\(\{[\s\S]*index: "LAST",[\s\S]*align: "end",[\s\S]*behavior: "auto"/,
  );
});

test("history positioning does not use the retrying bottom helper", () => {
  const blockStart = hookSource.indexOf(
    "if (\n      isCurrentHistoryCompletion &&",
  );
  const blockEnd = hookSource.indexOf(
    "\n\n  useEffect(() => {\n    if (sessionBottomScrollToken",
    blockStart,
  );
  const historyFinalizeBlock = hookSource.slice(blockStart, blockEnd);

  expect(blockStart).toBeGreaterThan(-1);
  expect(blockEnd).toBeGreaterThan(blockStart);
  expect(historyFinalizeBlock).not.toMatch(
    /requestScrollToBottom|requestAnimationFrame|setTimeout|ResizeObserver|forceScrollerToPhysicalBottom/,
  );
});
