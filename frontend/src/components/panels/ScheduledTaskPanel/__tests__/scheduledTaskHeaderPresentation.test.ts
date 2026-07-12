import { readFileSync } from "node:fs";
function source(path: string) {
  return readFileSync(new URL(path, import.meta.url), "utf8");
}

const panelSource = source("../index.tsx");
const statusFilterSource = source("../StatusFilter.tsx");
const panelControlsSource = source("../../../common/PanelControls.tsx");
const componentsCss = source("../../../../styles/components.css");

test("scheduled task header uses shared panel action styling", () => {
  expect(statusFilterSource).toMatch(/PanelFilterSelect/);
  expect(statusFilterSource).toMatch(/data-filter-menu/);
  expect(statusFilterSource).toMatch(/scheduledTask\.allStatuses/);
  expect(panelControlsSource).toMatch(/panel-filter-trigger/);
  expect(panelControlsSource).toMatch(/panel-filter-menu/);
  expect(panelControlsSource).toMatch(/panel-header-actions/);
  expect(componentsCss).toMatch(/\.panel-header-primary-action/);
  expect(panelSource).toMatch(/PanelHeaderActions/);
  expect(panelSource).toMatch(/scheduledTask\.create/);
  expect(panelSource).toMatch(/className="panel-header-primary-action"/);
  expect(panelSource).not.toMatch(
    /<select[\s\S]*?className="scheduled-task-input min-h-10 px-3 py-0"/,
  );
  expect(panelSource).not.toMatch(
    /className="scheduled-task-button scheduled-task-button--primary"/,
  );
});
