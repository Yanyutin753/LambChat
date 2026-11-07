import { readFileSync } from "node:fs";

const source = readFileSync(
  new URL("../ChatHeaderFrame.tsx", import.meta.url),
  "utf8",
);

test("keeps header padding while rendering the bottom gradient inside it", () => {
  expect(source).toMatch(
    /py-3[^"]*-mb-2[^"]*after:bottom-0[^"]*after:h-2[^"]*after:bg-\[linear-gradient\(to_bottom,var\(--theme-bg\),transparent\)\][^"]*"/,
  );
  expect(source).not.toContain("after:bottom-[-8px]");
});
