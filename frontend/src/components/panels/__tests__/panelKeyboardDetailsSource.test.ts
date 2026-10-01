import { readFileSync } from "node:fs";
import { expect, test } from "vitest";

test("role names expose a keyboard accessible detail button", () => {
  const roles = readFileSync(
    new URL("../RolesPanel.tsx", import.meta.url),
    "utf8",
  );
  expect(roles).toMatch(
    /<button[\s\S]*?className="role-card-title[\s\S]*?\{role\.name\}[\s\S]*?<\/button>/,
  );
});

test("markdown compact controls do not reset tap targets on every flex layout", () => {
  const css = readFileSync(
    new URL("../../../styles/markdown.css", import.meta.url),
    "utf8",
  );
  expect(css).not.toMatch(/\n {2}\.flex button,/);
  expect(css).not.toMatch(/button,\s*\[role="button"\]\s*\{\s*min-height:/);
});
