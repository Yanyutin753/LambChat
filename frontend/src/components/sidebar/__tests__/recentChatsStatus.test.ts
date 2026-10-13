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
  expect(source).toMatch(/getSessionTaskIndicator\(session\.metadata\?\.task_status\)/);
  expect(source).toMatch(/taskIndicator\.kind === "busy"/);
  expect(source).toMatch(/taskIndicator\.kind === "attention"/);
  expect(source).toMatch(/data-session-status="ask-human"/);
  expect(source).toMatch(/aria-label=\{runningLabel\}/);
  expect(source).toMatch(/LoadingSpinner/);
});

test("recent chats keeps status labels reachable via long-press tooltip, never forced open by row touch", () => {
  expect(source).toMatch(/<Tooltip/);
  expect(source).not.toMatch(/statusTooltipOpen/);
  expect(source).toMatch(/sidebar\.waitingHuman/);
});
