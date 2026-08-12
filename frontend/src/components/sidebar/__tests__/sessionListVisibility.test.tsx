import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = dirname(fileURLToPath(import.meta.url));

test("collapsed projects disable their session-list hook", () => {
  const source = readFileSync(resolve(__dirname, "../ProjectItem.tsx"), "utf8");

  expect(source).toMatch(
    /useFilteredSessionList\([\s\S]*?scrollRoot,[\s\S]*?isExpanded,[\s\S]*?\)/,
  );
});

test("closed recent chats guard the request function itself", () => {
  const source = readFileSync(
    resolve(__dirname, "../RecentChatsDialog.tsx"),
    "utf8",
  );
  const loadBody = source.match(
    /const loadSessions = useCallback\([\s\S]*?async \(reset = false\) => \{([\s\S]*?)\n {4}\},[\s\S]*?\);/,
  )?.[1];

  expect(loadBody).toBeTruthy();
  expect(loadBody).toMatch(/if \(!isOpen\) return/);
});
