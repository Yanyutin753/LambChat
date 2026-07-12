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
