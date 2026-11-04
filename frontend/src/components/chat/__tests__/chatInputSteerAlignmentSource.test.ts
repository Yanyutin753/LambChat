import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { expect, test } from "vitest";

test("queue shares the composer surface in normal flow without overlapping cards", () => {
  const source = readFileSync(
    resolve(__dirname, "../ChatInputSteerQueue.tsx"),
    "utf8",
  );
  expect(source).toContain("composer-queue");
  expect(source).not.toMatch(/-mb-|rounded-t-|chat-content-column/);
  const input = readFileSync(resolve(__dirname, "../ChatInput.tsx"), "utf8");
  expect(input.indexOf("<ChatInputSteerQueue")).toBeGreaterThan(
    input.indexOf('className="composer-workspace-shell"'),
  );
  expect(source).not.toMatch(
    /chat.queueGroup|chat.queueEditHint|min-w-\[7rem\]/,
  );
});
