import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, test } from "vitest";

describe("ChatInput queued steer alignment", () => {
  test("centers the queued steer row and aligns its status content", () => {
    const source = readFileSync(resolve(__dirname, "../ChatInput.tsx"), "utf8");

    expect(source).toMatch(
      /className="flex items-center gap-2 rounded-xl border px-3 py-2 text-sm"/,
    );
    expect(source).toMatch(
      /className="flex min-h-5 shrink-0 min-w-\[7rem\] items-center justify-center text-center text-xs"/,
    );
  });
});
