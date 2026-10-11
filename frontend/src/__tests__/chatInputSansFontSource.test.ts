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

test("editor chips keep sans while toolbar and mention entity names keep serif", () => {
  const css = readRepoFile("src/styles/chat.css");

  expect(css).toMatch(
    /\.chat-input-container\s+\.font-serif:not\(\s*\.mention-popup-name,\s*\.chat-input-toolbar,\s*\.chat-input-toolbar \*\s*\)\s*\{[^}]*font-family:\s*"Source Sans 3",\s*system-ui,\s*sans-serif/s,
  );
});
