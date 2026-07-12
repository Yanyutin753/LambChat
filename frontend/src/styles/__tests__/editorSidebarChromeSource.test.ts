import { readFileSync } from "node:fs";

const componentsSource = readFileSync(
  new URL("../components.css", import.meta.url),
  "utf8",
);

function cssRule(selector: string) {
  const normalizeSelector = (value: string) =>
    value
      .replace(/\s+/g, " ")
      .replace(/\s*,\s*/g, ",")
      .replace(/\(\s*/g, "(")
      .replace(/\s*\)/g, ")")
      .trim();
  const expectedSelector = normalizeSelector(selector);
  const normalizedSource = componentsSource
    .replace(/\/\*[\s\S]*?\*\//g, "")
    .replace(/\s+/g, " ")
    .replace(/\s*,\s*/g, ",")
    .replace(/\(\s*/g, "(")
    .replace(/\s*\)/g, ")");
  const ruleStart = normalizedSource.indexOf(`${expectedSelector} {`);

  if (ruleStart === -1) {
    return "";
  }

  const bodyStart = ruleStart + `${expectedSelector} {`.length;
  const bodyEnd = normalizedSource.indexOf(" }", bodyStart);

  return normalizedSource.slice(bodyStart, bodyEnd);
}

test("right sidebar chrome is shared by editor and tool sidebars", () => {
  const sharedRule = cssRule(
    ':where(.editor-sidebar--sidebar, .tool-console-panel[data-tool-panel-mode="sidebar"])',
  );

  expect(sharedRule).toContain("--right-sidebar-ring:");
  expect(sharedRule).toMatch(
    /height:\s*var\(--right-sidebar-height,\s*calc\(100% - 1\.5rem\)\);/,
  );
  expect(sharedRule).toMatch(/margin:\s*0\.75rem;/);
  expect(sharedRule).toMatch(/border-radius:\s*0\.75rem;/);
  expect(sharedRule).toMatch(/0 0 0 1px var\(--right-sidebar-ring\),/);
});

test("right sidebar dark chrome is shared by editor and tool sidebars", () => {
  const sharedRule = cssRule(
    ':is(.dark, .dark *) :where(.editor-sidebar--sidebar, .tool-console-panel[data-tool-panel-mode="sidebar"])',
  );

  expect(sharedRule).toContain("--right-sidebar-ring:");
});

test("editor sidebar desktop chrome matches tool sidebar treatment", () => {
  const editorRule = cssRule(".editor-sidebar--sidebar");

  expect(componentsSource).toMatch(
    /\.editor-sidebar\s*\{[\s\S]*?background:\s*linear-gradient/,
  );
  expect(editorRule).toMatch(
    /width:\s*calc\(var\(--editor-sidebar-width,\s*30%\) - 1\.5rem\);/,
  );
  expect(editorRule).toMatch(/--right-sidebar-height:\s*calc\(/);
});

test("generic sidebar preview panels reserve the same chrome inset", () => {
  const baseSource = readFileSync(
    new URL("../base.css", import.meta.url),
    "utf8",
  );
  const match = baseSource.match(
    /\[data-sidebar-panel\]\s*\{([\s\S]*?)\n\s*\}/,
  );
  const rule = match?.[1] ?? "";

  expect(rule).toMatch(
    /width:\s*calc\(var\(--sidebar-preview-width, 60%\) - 1\.5rem\) !important;/,
  );
  expect(rule).toMatch(
    /max-width:\s*calc\(var\(--sidebar-preview-width, 60%\) - 1\.5rem\) !important;/,
  );
});
