import { readFileSync } from "node:fs";
const source = readFileSync(
  new URL("../SubagentPanelContent.tsx", import.meta.url),
  "utf8",
);

test("subagent panel lets users pause auto-follow and jump back to the latest content", () => {
  expect(source).toMatch(/const \[showScrollToBottom, setShowScrollToBottom\]/);
  expect(source).toMatch(
    /userScrolledUpRef\.current = !isNearSubagentPanelBottom/,
  );
  expect(source).toMatch(/setShowScrollToBottom\(userScrolledUpRef\.current\)/);
  expect(source).toMatch(/const handleJumpToBottom = useCallback/);
  expect(source).toMatch(/userScrolledUpRef\.current = false/);
  expect(source).toMatch(/t\("common\.scrollToBottom"\)/);
  // A stretched sticky button translated by half its width clipped its label outside the panel.
  expect(source).toMatch(
    /className="absolute bottom-3 left-1\/2[^"\n]*\bw-max\b/,
  );
  expect(source).not.toMatch(/className="sticky bottom-3/);
});
