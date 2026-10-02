import { readFileSync } from "node:fs";
import { expect, test } from "vitest";

const read = (path: string) =>
  readFileSync(new URL(path, import.meta.url), "utf8");

test("message copy actions use the same idle and hover colors as sibling actions", () => {
  expect(read("../chat.css")).toMatch(
    /\.chat-message-actions \.copy-button\s*\{[^}]*@apply text-stone-400 dark:text-stone-400 hover:text-stone-600 dark:hover:text-stone-300;/,
  );
});

test("user and assistant action rows share button sizes and feedback spacing", () => {
  for (const file of ["index.tsx", "UserMessageBubble.tsx"]) {
    expect(read(`../../components/chat/ChatMessage/${file}`)).toContain(
      "chat-message-actions",
    );
  }
  const css = read("../chat.css");
  expect(css).toMatch(
    /\.chat-message-actions button,[\s\S]*?\{[^}]*width: 2rem;[^}]*height: 2rem;[^}]*padding: 0;/,
  );
  expect(css).toMatch(
    /\.chat-message-actions \.chat-message-feedback\s*\{\s*gap: inherit;/,
  );
});
