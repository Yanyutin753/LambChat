import { readFileSync } from "node:fs";
import { resolve } from "node:path";

function read(relativePath: string): string {
  return readFileSync(resolve(process.cwd(), relativePath), "utf8");
}

// 聊天列宽度契约：lg 用 5xl、xl 用 6xl（原始阶梯）。
// 列内所有元素必须共用同一阶梯，否则错位。
const WIDTH_LADDER = /max-w-4xl[^"]*lg:max-w-5xl[^"]*xl:max-w-6xl/;

test("message column, composer, skeletons and approval panel share the chat width ladder", () => {
  const sources = [
    "src/components/chat/ChatMessage/index.tsx",
    "src/components/chat/ChatMessage/UserMessageBubble.tsx",
    "src/components/chat/ChatInput.tsx",
    "src/components/chat/ChatInputSteerQueue.tsx",
    "src/components/skeletons/ChatSkeletons.tsx",
    "src/components/panels/ApprovalPanel.tsx",
  ];
  for (const source of sources) {
    expect(read(source)).toMatch(WIDTH_LADDER);
  }
});
