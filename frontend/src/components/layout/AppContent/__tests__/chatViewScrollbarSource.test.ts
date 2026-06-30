import test from "node:test";
import assert from "node:assert/strict";
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

function getCssRule(selector: string): string {
  const escapedSelector = selector.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  return (
    chatCss.match(new RegExp(`${escapedSelector}\\s*\\{[^}]*\\}`))?.[0] ?? ""
  );
}

test("chat message scroller hides native scrollbars without disabling scrolling", () => {
  assert.match(chatViewSource, /className=\{`chat-message-scroller /);
  assert.match(chatViewSource, /\$\{props\.className \?\? ""\}`\}/);
  assert.match(
    chatCss,
    /\.chat-message-scroller\s*\{[\s\S]*?scrollbar-width:\s*none;[\s\S]*?-ms-overflow-style:\s*none;/,
  );
  assert.match(
    chatCss,
    /\.chat-message-scroller::-webkit-scrollbar\s*\{[\s\S]*?display:\s*none;/,
  );
});

test("history restore hides the unstable measurement frame without removing layout", () => {
  const settlingRule = getCssRule(".chat-history-scroll-settling");
  const overlayRule = getCssRule(".chat-history-settling-overlay");

  assert.match(
    chatViewSource,
    /const shouldHideHistoryMeasurementFrame =\s*isLoadingHistory \|\| isHistoryScrollSettling;/,
  );
  assert.match(chatViewSource, /isHistoryScrollSettling/);
  assert.match(chatViewSource, /chat-history-scroll-settling/);
  assert.match(chatViewSource, /shouldHideHistoryMeasurementFrame && \(/);
  assert.match(chatViewSource, /chat-history-settling-overlay/);
  assert.match(settlingRule, /visibility:\s*hidden;/);
  assert.doesNotMatch(settlingRule, /display:\s*none/);
  assert.match(overlayRule, /position:\s*absolute;/);
  assert.match(overlayRule, /inset:\s*0;/);
});

test("history restore keeps a skeleton visible until measured bottom is stable", () => {
  assert.match(
    chatViewSource,
    /<div className="chat-history-settling-overlay"[\s\S]*<ChatSkeletonMessagesOnly count=\{8\} \/>[\s\S]*<\/div>/,
  );
});
