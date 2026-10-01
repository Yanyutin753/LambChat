import { readFileSync } from "node:fs";
import { expect, test } from "vitest";

const source = readFileSync(new URL("../Header.tsx", import.meta.url), "utf8");

test("header puts more before workspace and avatar with a consistent gap", () => {
  const right = source.slice(source.indexOf("{/* Right */}"));
  expect(right).toContain('className="flex items-center gap-2 flex-shrink-0"');
  expect(right.indexOf("<MoreHorizontal")).toBeLessThan(right.indexOf("{headerActions}"));
  expect(right.indexOf("{headerActions}")).toBeLessThan(right.indexOf("<UserMenu"));
});
