import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { expect, test } from "vitest";

test("keeps ChatAppContent within the frontend line budget margin", () => {
  const content = readFileSync(
    resolve(import.meta.dirname, "../ChatAppContent.tsx"),
    "utf8",
  );

  expect(content.split("\n").length).toBeLessThanOrEqual(970);
});
