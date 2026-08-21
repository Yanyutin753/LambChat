import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const source = readFileSync(resolve(__dirname, "../RecentChatsDialog.tsx"), "utf8");

test("recent chats renders the same task status indicators as the sidebar", () => {
  expect(source).toMatch(/task_status/);
  expect(source).toMatch(/taskStatus === "running" \|\| taskStatus === "pending"/);
  expect(source).toMatch(/taskStatus === "waiting_human"/);
  expect(source).toMatch(/data-session-status="ask-human"/);
  expect(source).toMatch(/title=\{t\(/);
  expect(source).toMatch(/aria-label=\{t\(/);
  expect(source).toMatch(/title="Ask human · 等待你的回复"/);
  expect(source).toMatch(/animate-spin/);
});
