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
  expect(chatViewSource).toMatch(/className=\{`chat-message-scroller /);
  expect(chatViewSource).toMatch(/\$\{props\.className \?\? ""\}`\}/);
  expect(chatCss).toMatch(
    /\.chat-message-scroller\s*\{[\s\S]*?scrollbar-width:\s*none;[\s\S]*?-ms-overflow-style:\s*none;/,
  );
  expect(chatCss).toMatch(
    /\.chat-message-scroller::-webkit-scrollbar\s*\{[\s\S]*?display:\s*none;/,
  );
});

test("history restore hides the unstable measurement frame without removing layout", () => {
  const settlingRule = getCssRule(".chat-history-scroll-settling");
  const overlayRule = getCssRule(".chat-history-settling-overlay");

  expect(chatViewSource).toMatch(
    /const shouldHideHistoryMeasurementFrame =\s*isLoadingHistory \|\| isHistoryScrollSettling;/,
  );
  expect(chatViewSource).toMatch(/isHistoryScrollSettling/);
  expect(chatViewSource).toMatch(/chat-history-scroll-settling/);
  expect(chatViewSource).toMatch(/shouldHideHistoryMeasurementFrame && \(/);
  expect(chatViewSource).toMatch(/chat-history-settling-overlay/);
  expect(settlingRule).toMatch(/visibility:\s*hidden;/);
  expect(settlingRule).not.toMatch(/display:\s*none/);
  expect(overlayRule).toMatch(/position:\s*absolute;/);
  expect(overlayRule).toMatch(/inset:\s*0;/);
});

test("history restore keeps a skeleton visible until measured bottom is stable", () => {
  expect(chatViewSource).toMatch(
    /<div className="chat-history-settling-overlay"[\s\S]*<ChatSkeletonMessagesOnly count=\{8\} \/>[\s\S]*<\/div>/,
  );
});
