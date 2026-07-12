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

test("drives the Virtuoso session key through state so session switches remount the message list", () => {
  expect(chatViewSource).toMatch(/setMessageListSessionKey/);
  expect(chatViewSource).toMatch(/key=\{messageListSessionKey\}/);
  expect(chatViewSource).not.toMatch(
    /key=\{messageListSessionKeyRef\.current\}/,
  );
});

test("does not reuse the Virtuoso remount key as a bottom-lock token", () => {
  expect(chatViewSource).not.toMatch(
    /useMessageScroll\([\s\S]*isLoadingHistory,\s*messageListSessionKey,\s*\)/,
  );
  expect(chatViewSource).toMatch(
    /useMessageScroll\([\s\S]*isLoadingHistory,\s*null,\s*\)/,
  );
});

test("lets Virtuoso follow output smoothly only outside history restore", () => {
  expect(chatViewSource).toMatch(
    /if \(shouldHideHistoryMeasurementFrame\) \{\s*return isAtBottom \? "auto" : false;\s*\}/,
  );
  expect(chatViewSource).toMatch(/return isAtBottom \? "smooth" : false;/);
  expect(chatViewSource).toMatch(/followOutput=\{handleVirtuosoFollowOutput\}/);
  expect(chatViewSource).not.toMatch(/followOutput=\{"smooth"\}/);
});

test("anchors floating scroll buttons to the chat input", () => {
  expect(chatViewSource).toMatch(
    /const FLOATING_SCROLL_BUTTON_OFFSET_CLASS = "bottom-full mb-3";/,
  );
  expect(
    chatViewSource.match(/\$\{FLOATING_SCROLL_BUTTON_OFFSET_CLASS\}/g)?.length,
  ).toBe(1);
  expect(chatViewSource).toMatch(
    /\{messages\.length > 0 && \(\s*<div className="relative">[\s\S]*<ChatInput\s+[\s\S]*\{\.\.\.chatInputProps\}[\s\S]*<\/div>\s*\)\}/,
  );
  expect(chatViewSource).not.toMatch(/bottom-[1-9]\d*/);
});

test("renders eight chat skeleton groups while loading history", () => {
  expect(chatViewSource).toMatch(/<ChatSkeleton count=\{8\} \/>/);
});
