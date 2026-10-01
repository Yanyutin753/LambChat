import { readFileSync } from "node:fs";
const toolbarSource = readFileSync(
  new URL("../DocumentPreviewToolbar.tsx", import.meta.url),
  "utf8",
);

test("document preview toolbar uses shared ToolbarIconButton for all actions", () => {
  expect(toolbarSource).toMatch(/import \{[\s\S]*ToolbarIconButton/);
  expect(toolbarSource).toMatch(/<ToolbarIconButton/);
  expect(toolbarSource).not.toMatch(/toolbarActionButtonClass/);
  expect(toolbarSource).not.toMatch(/desktopToolbarActionButtonClass/);
});

const styles = readFileSync(
  new URL("../../../styles/components.css", import.meta.url),
  "utf8",
);

test("document preview uses a reading column and quiet path disclosure", () => {
  const preview = readFileSync(
    new URL("../DocumentPreview.tsx", import.meta.url),
    "utf8",
  );
  expect(styles.includes(".document-reading-column")).toBe(true);
  expect(styles.includes(".right-panel-tab:only-child")).toBe(true);
  expect(preview.includes("<details")).toBe(true);
  expect(preview.includes("documents.pressEscToClose")).toBe(false);
});
