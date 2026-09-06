import {
  buildVisibleCategories,
  groupFilteredSettings,
} from "../settingsPanelGrouping";
import type { SettingItem } from "../../../types";

function setting(partial: Partial<SettingItem>): SettingItem {
  return {
    key: "SOME_KEY",
    value: true,
    type: "boolean",
    category: "frontend",
    subcategory: "",
    description: "some setting",
    default_value: true,
    requires_restart: false,
    is_sensitive: false,
    frontend_visible: true,
    ...partial,
  };
}

const categoryLabels = {
  frontend: "前端",
  llm: "模型",
} as Record<string, string>;

const subcategoryLabels = {
  display: "显示",
} as Record<string, string>;

test("buildVisibleCategories keeps CATEGORY_ORDER order and drops empty categories", () => {
  const byCategory = {
    llm: [setting({ key: "A" })],
    frontend: [setting({ key: "B" }), setting({ key: "C" })],
    redis: [],
  } as unknown as Parameters<typeof buildVisibleCategories>[0];

  expect(
    buildVisibleCategories(byCategory, () => true).map(
      ({ category, count }) => ({
        category,
        count,
      }),
    ),
  ).toEqual([
    { category: "frontend", count: 2 },
    { category: "llm", count: 1 },
  ]);
});

test("buildVisibleCategories filters items through the visibility predicate", () => {
  const byCategory = {
    frontend: [
      setting({ key: "VISIBLE", depends_on: undefined }),
      setting({ key: "HIDDEN" }),
    ],
  } as unknown as Parameters<typeof buildVisibleCategories>[0];

  const visible = buildVisibleCategories(
    byCategory,
    (s) => s.key === "VISIBLE",
  );
  expect(visible).toEqual([{ category: "frontend", count: 1 }]);
});

test("groupFilteredSettings groups by category label on global search", () => {
  const items = [
    setting({ key: "A", category: "frontend" }),
    setting({ key: "B", category: "llm" }),
    setting({ key: "C", category: "frontend" }),
  ];

  const groups = groupFilteredSettings(items, {
    isGlobalSearch: true,
    categoryLabels,
    subcategoryLabels,
  });

  expect(groups.map((g) => g.label)).toEqual(["前端", "模型"]);
  expect(groups[0].settings.map((s) => s.key)).toEqual(["A", "C"]);
});

test("groupFilteredSettings groups by subcategory when browsing a category", () => {
  const items = [
    setting({ key: "A", subcategory: "display" }),
    setting({ key: "B", subcategory: "unknown_scope" }),
    setting({ key: "C", subcategory: "" }),
    setting({ key: "D", subcategory: "display" }),
  ];

  const groups = groupFilteredSettings(items, {
    isGlobalSearch: false,
    categoryLabels,
    subcategoryLabels,
  });

  expect(groups.map((g) => g.label)).toEqual(["显示", "unknown_scope", ""]);
  expect(groups[0].settings.map((s) => s.key)).toEqual(["A", "D"]);
});
