import { readFileSync } from "node:fs";

const chatInputSource = readFileSync(
  new URL("../ChatInput.tsx", import.meta.url),
  "utf8",
);
const runningSendSource = readFileSync(
  new URL("../chatInputRunningSend.ts", import.meta.url),
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
  // Enter 去向守卫抽到 chatInputRunningSend；ask-human 期间只吞键不发送
  expect(runningSendSource).toMatch(/if \(state\.sendBlocked\) return;/);
  expect(chatInputSource).toMatch(/!sendBlocked/);
});

test("disables the send button while waiting for human input", () => {
  expect(toolbarSource).toMatch(/disabled=\{sendBlocked \|\| !canSubmit\}/);
  expect(chatInputSource).toMatch(/sendBlocked=\{sendBlocked\}/);
});

test("derives the composer block from pending ask-human parts", () => {
  // 每 tick 只算一次（useMemo），sendBlocked 复用结果
  expect(chatViewSource).toMatch(
    /const hasPendingAskHumanParts = useMemo\(\s*\(\) =>\s*hasPendingAskHuman\(messages\.flatMap/,
  );
  expect(chatViewSource).toMatch(
    /sendBlocked:\s*approvals\.length\s*>\s*0\s*\|\|\s*hasPendingAskHumanParts/,
  );
});
