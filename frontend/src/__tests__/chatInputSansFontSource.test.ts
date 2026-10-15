import { readFileSync } from "node:fs";
import { resolve } from "node:path";

/** 编辑器使用 sans，工具栏与 @ 提及实体名保留 serif。 */
function readRepoFile(...segments: string[]): string {
  return readFileSync(
    resolve(import.meta.dirname, "../..", ...segments),
    "utf8",
  );
}

test("chat input container opts into the sans stack, not the serif display font", () => {
  const source = readRepoFile("src/components/chat/ChatInput.tsx");

  expect(source).toMatch(/chat-input-container font-sans/);
  expect(source).not.toMatch(/chat-input-container font-serif/);
});

test("editor inherits sans while reference labels, toolbar and mention names retain serif", () => {
  const css = readRepoFile("src/styles/chat.css");
  const toolbar = readRepoFile("src/components/chat/ChatInputToolbar.tsx");
  const mentions = readRepoFile("src/components/chat/MentionPopup.tsx");
  const fileChip = readRepoFile("src/components/chat/richComposer/FileReferenceChip.tsx");

  expect(css).not.toMatch(/\.chat-input-container\s+\.font-serif:not/);
  expect(toolbar).toContain("chat-input-toolbar font-serif");
  expect(mentions).toContain("mention-popup-name font-serif");
  expect(fileChip).toContain("composer-reference-chip__label font-serif");
});
