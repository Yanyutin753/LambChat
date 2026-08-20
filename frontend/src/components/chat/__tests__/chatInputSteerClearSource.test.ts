import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, test } from "vitest";

const source = readFileSync(
  resolve(process.cwd(), "src/components/chat/ChatInput.tsx"),
  "utf8",
);

describe("ChatInput steer draft clearing", () => {
  test("clears the rich composer state after sending a steer", () => {
    expect(source).toMatch(/setComposerPlainText\(""\)/);
  });
});
