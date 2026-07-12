import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const currentDir = dirname(fileURLToPath(import.meta.url));
const frontendSrc = resolve(currentDir, "../..");

const localeFiles = ["en", "zh", "ja", "ko", "ru"].map((locale) =>
  resolve(frontendSrc, "i18n", "locales", `${locale}.json`),
);

function readJson(path: string) {
  return JSON.parse(readFileSync(path, "utf8"));
}

test("message fork strings are available in every locale", () => {
  for (const localeFile of localeFiles) {
    const locale = readJson(localeFile);
    expect(typeof locale.chat.message.fork).toBe("string");
    expect(typeof locale.chat.message.forkSuccess).toBe("string");
    expect(typeof locale.chat.message.forkFailed).toBe("string");
  }
});

test("fork message components use i18n keys instead of inline English text", () => {
  const files = [
    resolve(
      frontendSrc,
      "components",
      "chat",
      "ChatMessage",
      "UserMessageBubble.tsx",
    ),
    resolve(frontendSrc, "components", "chat", "ChatMessage", "index.tsx"),
    resolve(frontendSrc, "components", "layout", "AppContent", "ChatView.tsx"),
  ];

  for (const file of files) {
    const source = readFileSync(file, "utf8");
    expect(source.includes('title="Fork"')).toBe(false);
    expect(source.includes('"Forked to new session"')).toBe(false);
    expect(source.includes('"Fork failed"')).toBe(false);
  }
});
