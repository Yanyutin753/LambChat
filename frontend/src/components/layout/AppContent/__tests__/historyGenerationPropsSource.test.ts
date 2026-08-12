import { readFileSync } from "node:fs";
import { resolve } from "node:path";

function source(name: string): string {
  return readFileSync(
    resolve(process.cwd(), "src", "components", "layout", "AppContent", name),
    "utf8",
  );
}

test("passes the history generation from agent state into message scrolling", () => {
  const appContent = source("ChatAppContent.tsx");
  const props = source("ChatViewProps.tsx");
  const view = source("ChatView.tsx");

  expect(appContent).toMatch(/historyLoadGeneration,/);
  expect(appContent).toMatch(
    /<ChatView[\s\S]*historyLoadGeneration=\{historyLoadGeneration\}/,
  );
  expect(props).toMatch(/historyLoadGeneration: number;/);
  expect(view).toMatch(
    /useMessageScroll\([\s\S]*isLoadingHistory,\s*historyLoadGeneration,\s*null,\s*\)/,
  );
});
