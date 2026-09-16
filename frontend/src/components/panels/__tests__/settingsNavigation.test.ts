import {
  buildSettingsNavigation,
  filterSettings,
  SETTINGS_NAV_GROUPS,
} from "../settingsNavigation";
import { CATEGORY_ORDER } from "../SettingsPanel.constants";
import type { SettingItem } from "../../../types";

const item = (overrides: Partial<SettingItem> = {}): SettingItem => ({
  key: "THEME",
  category: "frontend",
  subcategory: "display",
  description: "theme.description",
  type: "string",
  value: "light",
  default_value: "light",
  requires_restart: false,
  is_sensitive: false,
  frontend_visible: true,
  ...overrides,
});

test("every existing category belongs to exactly one navigation group", () => {
  const categories = SETTINGS_NAV_GROUPS.flatMap((group) => group.categories);
  expect([...categories].sort()).toEqual([...CATEGORY_ORDER].sort());
  expect(new Set(categories).size).toBe(categories.length);
});

test("navigation omits empty groups and preserves category counts", () => {
  expect(
    buildSettingsNavigation([
      { category: "llm", count: 3 },
      { category: "frontend", count: 2 },
    ]),
  ).toEqual([
    { id: "experience", categories: [{ category: "frontend", count: 2 }] },
    { id: "intelligence", categories: [{ category: "llm", count: 3 }] },
  ]);
});

const options = {
  query: "",
  category: "frontend",
  subcategory: null,
  isVisible: () => true,
  translate: (key: string) => (key === "theme.description" ? "界面主题" : key),
  categoryLabels: { frontend: "基础体验" },
  subcategoryLabels: { display: "外观显示" },
} as const;

test("administrators can browse and search settings reserved for management", () => {
  const items = [item({ frontend_visible: false })];
  for (const query of ["", "THEME"]) {
    expect(
      filterSettings(items, { ...options, query, includeAdmin: true }),
    ).toEqual(items);
  }
});

test("server navigation controls group and category order", () => {
  expect(
    buildSettingsNavigation(
      [
        { category: "frontend", count: 2 },
        { category: "llm", count: 1 },
      ],
      [{ id: "intelligence", categories: ["llm", "frontend"] }],
    ),
  ).toEqual([
    {
      id: "intelligence",
      categories: [
        { category: "llm", count: 1 },
        { category: "frontend", count: 2 },
      ],
    },
  ]);
});

test("whitespace search stays in the selected category", () => {
  expect(
    filterSettings([item(), item({ category: "llm" })], {
      ...options,
      query: "  ",
    }),
  ).toHaveLength(1);
});

test("search matches translated category, subcategory and description globally", () => {
  for (const query of ["基础体验", "外观显示", "界面主题", " theme "]) {
    expect(
      filterSettings([item()], { ...options, category: "llm", query }),
    ).toHaveLength(1);
  }
});

test("hidden and dependency-disabled settings never appear in search or browsing", () => {
  for (const query of ["", "THEME"]) {
    expect(
      filterSettings(
        [item({ frontend_visible: false }), item({ key: "DISABLED_THEME" })],
        {
          ...options,
          query,
          isVisible: (setting) => setting.key !== "DISABLED_THEME",
        },
      ),
    ).toEqual([]);
  }
});

test("subcategory filter narrows browsing but does not restrict global search", () => {
  const items = [
    item(),
    item({
      key: "OTHER",
      subcategory: "contact",
      description: "contact.description",
    }),
  ];
  expect(
    filterSettings(items, { ...options, subcategory: "contact" }).map(
      (s) => s.key,
    ),
  ).toEqual(["OTHER"]);
  expect(
    filterSettings(items, {
      ...options,
      subcategory: "contact",
      query: "THEME",
    }).map((s) => s.key),
  ).toEqual(["THEME"]);
});
