import { readFileSync } from "node:fs";
import { resolve } from "node:path";

const chatViewSource = readFileSync(
  resolve(
    process.cwd(),
    "src",
    "components",
    "layout",
    "AppContent",
    "ChatView.tsx",
  ),
  "utf8",
);

const chatCss = readFileSync(
  resolve(process.cwd(), "src", "styles", "chat.css"),
  "utf8",
);

test("chat message scroller hides native scrollbars without disabling scrolling", () => {
  expect(chatViewSource).toMatch(/className=\{`chat-message-scroller /);
  expect(chatViewSource).toMatch(/\$\{props\.className \?\? ""\}`\}/);
  expect(chatCss).toMatch(
    /\.chat-message-scroller\s*\{[\s\S]*?scrollbar-width:\s*none;[\s\S]*?-ms-overflow-style:\s*none;/,
  );
  expect(chatCss).toMatch(
    /\.chat-message-scroller::-webkit-scrollbar\s*\{[\s\S]*?display:\s*none;/,
  );
});

test("history restore renders directly without a settling overlay", () => {
  expect(chatViewSource).not.toMatch(/isHistoryScrollSettling/);
  expect(chatViewSource).not.toMatch(/chat-history-scroll-settling/);
  expect(chatViewSource).not.toMatch(/chat-history-settling-overlay/);
  expect(chatCss).not.toMatch(/\.chat-history-scroll-settling/);
  expect(chatCss).not.toMatch(/\.chat-history-settling-overlay/);
  expect(chatViewSource).toMatch(/\{messages\.length > 0 && \(/);
});
