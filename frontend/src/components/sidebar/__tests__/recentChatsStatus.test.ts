import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const source = readFileSync(
  resolve(__dirname, "../RecentChatsDialog.tsx"),
  "utf8",
);

test("recent chats renders the same task status indicators as the sidebar", () => {
  expect(source).toMatch(/task_status/);
  expect(source).toMatch(
    /taskStatus === "running" \|\| taskStatus === "pending"/,
  );
  expect(source).toMatch(/taskStatus === "waiting_human"/);
  expect(source).toMatch(/data-session-status="ask-human"/);
  expect(source).toMatch(/aria-label=\{runningLabel\}/);
  expect(source).toMatch(/animate-spin/);
});

test("recent chats surfaces status labels as touch tooltips, not inline text", () => {
  expect(source).toMatch(/<Tooltip/);
  expect(source).toMatch(/open=\{statusTooltipOpen\}/);
  expect(source).toMatch(/handleRowTouchStart/);
  expect(source).toMatch(/touchedSessionId/);
  expect(source).toMatch(/sidebar\.waitingHuman/);
});
