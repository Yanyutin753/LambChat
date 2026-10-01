import { readFileSync } from "node:fs";
import { expect, test } from "vitest";

test("composer action groups share spacing and desktop hover uses a softer radius", () => {
  const toolbar = readFileSync(new URL("../../components/chat/ChatInputToolbar.tsx", import.meta.url), "utf8");
  const desktop = readFileSync(new URL("../desktop.css", import.meta.url), "utf8");
  expect(toolbar.match(/items-center gap-1\.5/g)).toHaveLength(2);
  expect(toolbar).toMatch(/chat-input-toolbar[^"\n]*gap-1\.5/);
  expect(desktop).toMatch(/\.chat-input-toolbar\s*\{[^}]*gap:\s*0\.375rem/);
  expect(desktop).toMatch(/\.chat-tool-btn\s*\{\s*border-radius:\s*var\(--radius-lg\)/);
});
