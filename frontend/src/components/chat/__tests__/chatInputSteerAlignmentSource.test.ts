import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { expect, test } from "vitest";

test("queue shares the composer surface without permanent headings and hints", () => {
  const source = readFileSync(
    resolve(__dirname, "../ChatInputSteerQueue.tsx"),
    "utf8",
  );
  expect(source).toContain("-mb-5 rounded-t-3xl");
  expect(source).not.toMatch(
    /chat.queueGroup|chat.queueEditHint|min-w-\[7rem\]/,
  );
});
