import test from "node:test";
import assert from "node:assert/strict";
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
  assert.match(
    hookSource,
    /import \{ useRef, useEffect, useLayoutEffect, useState, useCallback \} from "react";/,
  );
  assert.match(
    hookSource,
    /useLayoutEffect\(\(\) => \{[\s\S]*shouldFinalizeHistoryLoadScroll[\s\S]*requestScrollToBottom\("history-finalize"/,
  );
});

test("keeps history skeleton visible until the full settle observation completes", () => {
  assert.match(
    hookSource,
    /requestScrollToBottom\("history-finalize",\s*\{\s*onComplete: clearHistoryScrollSettling,\s*\}\)/,
  );
  assert.doesNotMatch(
    hookSource,
    /requestScrollToBottom\("history-finalize",\s*\{[\s\S]*onInitialSettle:\s*clearHistoryScrollSettling/,
  );
});
