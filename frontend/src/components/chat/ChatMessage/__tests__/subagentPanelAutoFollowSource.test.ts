import { readFileSync } from "node:fs";
const source = readFileSync(
  new URL("../SubagentBlocks.tsx", import.meta.url),
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
});
