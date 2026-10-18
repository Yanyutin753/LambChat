import { readFileSync } from "node:fs";
import { resolve } from "node:path";

function read(relativePath: string): string {
  return readFileSync(resolve(process.cwd(), relativePath), "utf8");
}

// Messages, input and transient states must use the same responsive column.
test("message column, composer, skeletons and approval panel share the chat column", () => {
  const sources = [
    "src/components/chat/ChatMessage/index.tsx",
    "src/components/chat/ChatMessage/UserMessageBubble.tsx",
    "src/components/chat/ChatInput.tsx",
    "src/components/chat/ChatInputSteerQueue.tsx",
    "src/components/chat/SessionTodoDock.tsx",
    "src/components/skeletons/ChatSkeletons.tsx",
    "src/components/panels/ApprovalPanel.tsx",
  ];
  for (const source of sources) {
    expect(read(source)).toContain("chat-content-column");
    expect(read(source)).not.toMatch(/max-w-4xl[^"\n]*lg:max-w-5xl/);
  }
});

test("conversation editor spacing does not target the welcome composer", () => {
  const css = read("src/styles/chat.css");
  expect(css).toContain(".chat-conversation-composer");
  expect(css).not.toMatch(
    /\.chat-view-content-region\s+\.chat-input-container/,
  );
  expect(read("src/components/chat/ChatInput.tsx")).toContain(
    'className ?? "chat-content-column chat-conversation-composer"',
  );
});
