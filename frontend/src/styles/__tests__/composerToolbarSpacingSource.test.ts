import { readFileSync } from "node:fs";
import { expect, test } from "vitest";

test("composer action groups share spacing and desktop hover uses a softer radius", () => {
  const toolbar = readFileSync(
    new URL("../../components/chat/ChatInputToolbar.tsx", import.meta.url),
    "utf8",
  );
  const desktop = readFileSync(
    new URL("../desktop.css", import.meta.url),
    "utf8",
  ).replace(/\s+/g, " ");
  expect(toolbar.match(/items-center gap-2\.5/g)).toHaveLength(3);
  expect(toolbar).toMatch(/chat-input-toolbar[^"\n]*gap-2\.5/);
  expect(desktop).toMatch(/\.chat-input-toolbar\s*\{[^}]*gap:\s*0\.625rem/);
  expect(desktop).toMatch(
    /\.chat-tool-btn\s*\{\s*border-radius:\s*var\(--radius-md\)/,
  );
});

test("desktop toolbar uses equal insets and square icon actions", () => {
  const desktop = readFileSync(
    new URL("../desktop.css", import.meta.url),
    "utf8",
  ).replace(/\s+/g, " ");
  expect(desktop).toMatch(
    /\.chat-input-toolbar\s*\{[^}]*padding:\s*0\.625rem;[^}]*margin:\s*0;/,
  );
  expect(desktop).toMatch(
    /\.chat-input-toolbar > div > button\s*\{[^}]*height:\s*2\.5rem;[^}]*min-width:\s*2\.5rem;/,
  );
  expect(desktop).toMatch(
    /\.chat-input-toolbar \.chat-tool-btn\s*\{[^}]*padding:\s*0\.75rem;/,
  );
});

test("desktop composer gives the bottom actions more breathing room and height", () => {
  const desktop = readFileSync(
    new URL("../desktop.css", import.meta.url),
    "utf8",
  ).replace(/\s+/g, " ");
  expect(desktop).toMatch(
    /@media \(min-width: 640px\)\s*\{[^]*?\.chat-input-toolbar\s*\{[^}]*padding:\s*0\.625rem/,
  );
  expect(desktop).toMatch(
    /\.chat-input-toolbar :is\(\.chat-tool-btn, \.skeleton-line\.h-9\),[^]*?\.chat-input-toolbar > div > button\s*\{[^}]*height:\s*2\.5rem/,
  );
  const skeleton = readFileSync(
    new URL("../../components/skeletons/ChatSkeletons.tsx", import.meta.url),
    "utf8",
  );
  expect(skeleton).toMatch(/className="chat-input-toolbar /);
});

test("send control stays circular in every state", () => {
  const chat = readFileSync(new URL("../chat.css", import.meta.url), "utf8");
  expect(chat).toMatch(/\.chat-send-button\s*\{[^}]*border-radius:\s*50%/);
});

test("toolbar retains left and right action groups", () => {
  const toolbar = readFileSync(
    new URL("../../components/chat/ChatInputToolbar.tsx", import.meta.url),
    "utf8",
  );
  expect(toolbar).toMatch(/chat-input-toolbar[^"\n]*justify-between/);
  expect(toolbar).toMatch(/min-h-9 min-w-0 flex-1/);
});
