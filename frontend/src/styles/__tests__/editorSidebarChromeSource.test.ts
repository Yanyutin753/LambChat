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
    /width:\s*calc\(var\(--editor-sidebar-width,\s*34%\) - 1\.5rem\);/,
  );
  expect(editorRule).toMatch(/--right-sidebar-height:\s*calc\(/);
});

test("the app reserves space for one active docked right-panel lane", () => {
  const baseSource = readFileSync(
    new URL("../base.css", import.meta.url),
    "utf8",
  );
  expect(baseSource).toMatch(
    /html\[data-right-panel-presentation="docked"\]\s+#root\s*\{[\s\S]*?max-width:\s*calc\(100% - var\(--right-panel-active-width, 0px\)\)/,
  );
  expect(baseSource).not.toMatch(
    /data-sidebar-preview="open"\]\[data-editor-sidebar="open"/,
  );
});
