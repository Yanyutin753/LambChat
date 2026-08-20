import { readFileSync } from "node:fs";

const chatInputSource = readFileSync(
  new URL("../ChatInput.tsx", import.meta.url),
  "utf8",
);
const toolbarSource = readFileSync(
  new URL("../ChatInputToolbar.tsx", import.meta.url),
  "utf8",
);
const chatViewSource = readFileSync(
  new URL("../../layout/AppContent/ChatView.tsx", import.meta.url),
  "utf8",
);

test("blocks keyboard submission while waiting for human input", () => {
  expect(chatInputSource).toMatch(/if \(sendBlocked\) \{/);
  expect(chatInputSource).toMatch(/!sendBlocked/);
});

test("disables the send button while waiting for human input", () => {
  expect(toolbarSource).toMatch(/disabled=\{sendBlocked \|\| !canSubmit\}/);
  expect(chatInputSource).toMatch(/sendBlocked=\{sendBlocked\}/);
});

test("derives the composer block from pending ask-human parts", () => {
  expect(chatViewSource).toMatch(
    /sendBlocked:\s*approvals\.length\s*>\s*0\s*\|\|\s*hasPendingAskHuman\(/,
  );
});
