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

test("small-screen right panels fill the viewport instead of acting like sheets", () => {
  const mobileRule = cssRule(".editor-sidebar--mobile");

  expect(mobileRule).toMatch(/top:\s*var\(--app-safe-area-top-active/);
  expect(mobileRule).toMatch(/height:\s*auto/);
  expect(mobileRule).toMatch(/max-height:\s*none/);
  expect(mobileRule).toMatch(/border-radius:\s*0/);
  expect(componentsSource).toMatch(
    /\[data-right-panel-root\]\[data-panel-presentation="fullscreen"\][\s\S]*?inset:\s*0/,
  );
});

test("right panel resizing exposes visible hover and keyboard focus states", () => {
  expect(componentsSource).toMatch(
    /:where\(\.right-panel-resize-handle, \.tool-console-resize-handle\):focus-visible[\s\S]*?outline:/,
  );
});

test("right panel motion respects reduced-motion preferences", () => {
  expect(componentsSource).toMatch(
    /@media \(prefers-reduced-motion: reduce\)[\s\S]*?\.editor-sidebar[\s\S]*?animation:\s*none/,
  );
  expect(componentsSource).toMatch(
    /@media \(prefers-reduced-motion: reduce\)[\s\S]*?\.tool-console-body__content[\s\S]*?transition-duration:\s*0\.01ms/,
  );
});
