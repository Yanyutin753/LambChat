import { CATEGORY_ORDER } from "../SettingsPanel.constants";
import {
  buildCategoryLabels,
  buildSubcategoryLabels,
} from "../settingsPanelLabels";

test("category labels cover every entry in CATEGORY_ORDER", () => {
  const labels = buildCategoryLabels((key) => key);
  expect(Object.keys(labels).sort()).toEqual([...CATEGORY_ORDER].sort());
  for (const category of CATEGORY_ORDER) {
    expect(labels[category]).toBeTruthy();
  }
});

test("subcategory labels pass translation keys through and stay non-empty", () => {
  const labels = buildSubcategoryLabels((key) => `t:${key}`);
  const entries = Object.entries(labels);
  expect(entries.length).toBeGreaterThan(0);
  for (const [, label] of entries) {
    expect(label).toMatch(/^t:/);
  }
});
