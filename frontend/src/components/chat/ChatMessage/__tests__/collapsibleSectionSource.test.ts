import { readFileSync } from "node:fs";

test("collapsible section header does not nest action buttons inside the toggle", () => {
  const componentSource = readFileSync(
    new URL("../CollapsibleSection.tsx", import.meta.url),
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

test("expanded collapsible section cards fill the available panel height", () => {
  const sectionSource = readFileSync(
    new URL("../CollapsibleSection.tsx", import.meta.url),
    "utf8",
  );
  const panelSource = readFileSync(
    new URL("../SubagentPanelContent.tsx", import.meta.url),
    "utf8",
  );

  expect(panelSource).toMatch(
    /className="flex min-h-0 flex-1 flex-col space-y-3"/,
  );
  expect(sectionSource).toMatch(
    /<div\s+data-sidebar-snapshot-key=\{`\$\{sectionKey\}-content`\}\s+className="mt-2 flex-1 min-h-0 overflow-y-auto animate-\[fade-in_150ms_ease-out\]"\s*>/,
  );
  expect(sectionSource).toMatch(/expanded && expandedClassName/);
  expect(panelSource).toMatch(
    /title=\{t\("chat\.message\.result"\)\}[\s\S]*?expandedClassName="flex min-h-0 flex-col grow shrink-0"/,
  );
});
