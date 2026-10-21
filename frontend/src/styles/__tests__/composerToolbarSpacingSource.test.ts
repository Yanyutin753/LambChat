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

test("desktop toolbar uses symmetric insets and square icon actions", () => {
  const desktop = readFileSync(
    new URL("../desktop.css", import.meta.url),
    "utf8",
  ).replace(/\s+/g, " ");
  expect(desktop).toMatch(
    /\.chat-input-toolbar\s*\{[^}]*padding:\s*var\(--composer-vertical-inset\) 0\.75rem;[^}]*margin:\s*0;/,
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
    /@media \(min-width: 640px\)\s*\{[^]*?\.chat-input-toolbar\s*\{[^}]*padding:\s*var\(--composer-vertical-inset\)/,
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

test("conversation toolbar keeps equal top and bottom spacing with fixed side insets", () => {
  const chat = readFileSync(new URL("../chat.css", import.meta.url), "utf8");
  const rules = [
    ...chat.matchAll(
      /\.chat-conversation-composer\s+\.chat-input-container:not\(\[data-composer-expanded\]\)\s+\.chat-input-toolbar\s*\{([^}]+)\}/g,
    ),
  ].map((match) => match[1]);
  expect(rules).toHaveLength(2);
  expect(rules[0]).toMatch(/padding-inline:\s*0\.75rem;/);
  expect(rules[1]).toMatch(/padding-inline:\s*0\.5rem;/);
  expect(chat).toMatch(
    /\.chat-input-toolbar\s*\{[^}]*padding-block:\s*var\(--composer-vertical-inset\);/,
  );
  const desktop = readFileSync(
    new URL("../desktop.css", import.meta.url),
    "utf8",
  );
  const narrow = desktop.match(
    /@container composer \(max-width: 320px\) \{([\s\S]*?)\n\}/,
  )?.[1];
  expect(narrow).not.toMatch(/padding-inline:/);
});

test("typing area does not add a second bottom gap above the toolbar", () => {
  const chat = readFileSync(new URL("../chat.css", import.meta.url), "utf8");
  const editor = chat.match(
    /(?:^|\n)\.chat-input-container:not\(\[data-composer-expanded\]\)\s+:is\(\.rich-chat-composer__editor, \[data-composer-editor-skeleton\]\)\s*\{([^}]+)\}/,
  )?.[1];
  expect(editor).toMatch(
    /min-height:\s*calc\(1\.55em \+ var\(--composer-vertical-inset\)\);/,
  );
  expect(editor).toMatch(
    /padding-block:\s*var\(--composer-vertical-inset\) 0;/,
  );
  expect(chat).not.toMatch(
    /\.chat-conversation-composer\s+\.chat-input-container:not\(\[data-composer-expanded\]\)\s+\.rich-chat-composer__editor\s*\{[^}]*min-height:\s*3rem;/,
  );
});

test("welcome input uses the shared content height instead of reserving empty lines", () => {
  const welcome = readFileSync(
    new URL("../welcome.css", import.meta.url),
    "utf8",
  );
  expect(welcome).not.toMatch(
    /:is\(\.rich-chat-composer__editor, \[data-composer-editor-skeleton\]\)\s*\{[^}]*min-height:/,
  );
  const chat = readFileSync(new URL("../chat.css", import.meta.url), "utf8");
  expect(welcome).not.toMatch(/\.welcome-input \.chat-composer-editor-wrap/);
  expect(chat).toMatch(
    /\.chat-input-container\s*\{[^}]*--composer-vertical-inset:\s*1\.25rem;/,
  );
  expect(chat).toMatch(
    /@media \(max-width: 639px\)\s*\{\s*\.chat-input-container\s*\{\s*--composer-vertical-inset:\s*1rem;/,
  );
  expect(chat).toMatch(
    /\.chat-input-container:not\(\[data-composer-expanded\]\)\s+\.chat-composer-editor-wrap\s*\{\s*padding-top:\s*0;/,
  );
});
