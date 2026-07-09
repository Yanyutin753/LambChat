import { readFileSync } from "node:fs";
test("collapsible section header does not nest action buttons inside the toggle", () => {
  const componentSource = readFileSync(
    new URL("../SubagentBlocks.tsx", import.meta.url),
    "utf8",
  );
  const componentsCss = readFileSync(
    new URL("../../../../styles/components.css", import.meta.url),
    "utf8",
  );

  expect(componentSource).not.toMatch(
    /<button[\s\S]*?\{action && <span onClick=\{\(e\) => e\.stopPropagation\(\)\}>\{action\}<\/span>\}[\s\S]*?<\/button>/,
  );
  expect(componentSource).toMatch(
    /<button[\s\S]*?aria-expanded=\{expanded\}[\s\S]*?onClick=\{toggleExpanded\}/,
  );
  expect(componentSource).toMatch(
    /\{action && <div className="shrink-0">\{action\}<\/div>\}/,
  );
  expect(componentSource).toMatch(
    /"collapsible-section-card--default bg-theme-bg-card border border-theme-border shadow-sm"/,
  );
  expect(componentSource).not.toMatch(/:\s*"bg-theme-bg-subtle"/);
  expect(componentsCss).toMatch(
    /\.collapsible-section-card--default\s*\{[\s\S]*?background:\s*var\(--theme-bg-card\);[\s\S]*?box-shadow:/,
  );
});
