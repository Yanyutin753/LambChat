import { readFileSync } from "node:fs";
import { expect, test } from "vitest";

test("composer action groups share spacing and desktop hover uses a softer radius", () => {
  const toolbar = readFileSync(new URL("../../components/chat/ChatInputToolbar.tsx", import.meta.url), "utf8");
  const desktop = readFileSync(new URL("../desktop.css", import.meta.url), "utf8");
  expect(toolbar.match(/items-center gap-1\.5/g)).toHaveLength(3);
  expect(toolbar).toMatch(/chat-input-toolbar[^"\n]*gap-1\.5/);
  expect(desktop).toMatch(/\.chat-input-toolbar\s*\{[^}]*gap:\s*0\.375rem/);
  expect(desktop).toMatch(/\.chat-tool-btn\s*\{\s*border-radius:\s*var\(--radius-lg\)/);
});

test("desktop toolbar uses equal insets and square icon actions", () => {
  const desktop = readFileSync(new URL("../desktop.css", import.meta.url), "utf8");
  expect(desktop).toMatch(/\.chat-input-toolbar\s*\{[^}]*padding:\s*0\.625rem;[^}]*margin:\s*0;/);
  expect(desktop).toMatch(/\.chat-input-toolbar > div > button\s*\{[^}]*height:\s*2\.5rem;[^}]*min-width:\s*2\.5rem;/);
  expect(desktop).toMatch(/\.chat-input-toolbar \.chat-tool-btn\s*\{[^}]*padding:\s*0\.75rem;/);
});

test("desktop composer gives the bottom actions more breathing room and height", () => {
  const desktop = readFileSync(new URL("../desktop.css", import.meta.url), "utf8");
  expect(desktop).toMatch(/@media \(min-width: 640px\)\s*\{[^]*?\.chat-input-toolbar\s*\{[^}]*padding:\s*0\.625rem/);
  expect(desktop).toMatch(/\.chat-input-toolbar :is\(\.chat-tool-btn, \.skeleton-line\.h-9\),[^]*?\.chat-input-toolbar > div > button\s*\{[^}]*height:\s*2\.5rem/);
  const skeleton = readFileSync(new URL("../../components/skeletons/ChatSkeletons.tsx", import.meta.url), "utf8");
  expect(skeleton).toMatch(/className="chat-input-toolbar /);
});
