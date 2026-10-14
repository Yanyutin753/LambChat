import { readFileSync } from "node:fs";
import { expect, test } from "vitest";

test("all role card metadata uses the same centered line height", () => {
  const source = readFileSync(
    new URL("../RolesPanel.tsx", import.meta.url),
    "utf8",
  );
  const metadata = source
    .split("{/* Header badges */}")[1]
    .split("{/* Title & description */}")[0];
  expect(metadata).toMatch(
    /flex flex-wrap items-center gap-2 mb-2 text-11 leading-none/,
  );
  expect(metadata).not.toMatch(/py-1 text-11|className="text-11 /);
  expect(metadata).toMatch(/<ShieldCheck size=\{11\} className="shrink-0"/);
});
