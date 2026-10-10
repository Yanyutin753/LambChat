import { readFileSync } from "node:fs";
import { resolve } from "node:path";

/**
 * 输入区（chat-input-container 盒内）走 sans（中文落系统黑体），衬线
 * 只保留给全站展示位（标题/实体名等）。盒内子组件自带的 font-serif
 * 由 chat.css 的作用域规则压回 sans；@ 提及弹窗的实体名除外——它
 * 跟随全站实体名衬线体系（见 entityNameSerifSource.test.ts）。
 */
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

test("font-serif chips inside the input box are scoped back to sans, mention entity names keep serif", () => {
  const css = readRepoFile("src/styles/chat.css");

  expect(css).toMatch(
    /\.chat-input-container \.font-serif:not\(\.mention-popup-name\)\s*\{[^}]*font-family:\s*"Source Sans 3",\s*system-ui,\s*sans-serif/s,
  );
});
