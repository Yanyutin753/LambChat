import { readFileSync } from "node:fs";
import { resolve } from "node:path";

const chatViewSource = readFileSync(
  resolve(process.cwd(), "src/components/layout/AppContent/ChatView.tsx"),
  "utf8",
);
const chatInputSource = readFileSync(
  resolve(process.cwd(), "src/components/chat/ChatInput.tsx"),
  "utf8",
);
const chatInputTypesSource = readFileSync(
  resolve(process.cwd(), "src/components/chat/chatInputTypes.ts"),
  "utf8",
);

test("keeps pending steer items out of the Virtuoso message list", () => {
  expect(chatViewSource).not.toMatch(
    /mergeMessagesWithSteers\(messages,\s*steerMessages/,
  );
  expect(chatViewSource).toMatch(/steerMessages,\s*onCancelSteer/);
});

test("renders pending steer items above the composer", () => {
  expect(chatInputTypesSource).toMatch(/steerMessages\?:/);
  // 渲染移入 ChatInputSteerQueue（steerMessages.map 在队列组件内执行）；
  // onEdit 提供排队消息「弹回输入框编辑」（Codex edit_queued_message）
  expect(chatInputSource).toMatch(
    /<ChatInputSteerQueue\s+items=\{steerMessages\}\s+onCancel=\{onCancelSteer\}\s+onEdit=/,
  );
});
