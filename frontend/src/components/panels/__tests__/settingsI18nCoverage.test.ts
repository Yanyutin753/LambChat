/** 设置面板 i18n 覆盖门禁：后端定义引用的 settingDesc.* 与全部 subcategory
 * 标签必须在五语齐全、且 settingsPanelLabels 映射表同步——缺一处直接挂 CI
 * （此前 18 个子类标签五语全缺，面板裸显英文 id）。 */

import { readFileSync, readdirSync } from "node:fs";
import { resolve, dirname } from "node:path";
import { fileURLToPath } from "node:url";
import { SETTINGS_NAV_GROUPS } from "../settingsNavigation";
import { CATEGORY_ORDER } from "../SettingsPanel.constants";

const repoRoot = resolve(
  dirname(fileURLToPath(import.meta.url)),
  "../../../../..",
);
const localeDir = resolve(repoRoot, "frontend/src/i18n/locales");
const defDir = resolve(repoRoot, "src/kernel/config");

function readRepoFile(rel: string): string {
  return readFileSync(resolve(repoRoot, rel), "utf8");
}

const descKeys = new Set<string>();
const subcats = new Set<string>();
for (const f of readdirSync(defDir)) {
  if (!f.startsWith("_definitions") || !f.endsWith(".py")) continue;
  const src = readFileSync(resolve(defDir, f), "utf8");
  for (const m of src.matchAll(/settingDesc\.([A-Z0-9_]+)/g))
    descKeys.add(m[1]);
  for (const m of src.matchAll(/"subcategory":\s*"([a-z0-9_]+)"/g))
    subcats.add(m[1]);
}

const locales = ["zh", "en", "ja", "ko", "ru"] as const;

test("legacy-server fallback preserves the backend navigation taxonomy", () => {
  const schema = readRepoFile("src/kernel/schemas/setting.py");
  const values = Object.fromEntries(
    [...schema.matchAll(/([A-Z_0-9]+) = "([a-z0-9_]+)"/g)].map((match) => [
      match[1],
      match[2],
    ]),
  );
  const catalog = readRepoFile("src/kernel/settings_navigation.py");
  const groups = [
    ...catalog.matchAll(
      /SettingsNavigationGroup\(\s*id="([^"]+)",\s*categories=\[([\s\S]*?)\]/g,
    ),
  ].map((match) => ({
    id: match[1],
    categories: [...match[2].matchAll(/SettingCategory\.([A-Z_0-9]+)/g)].map(
      (category) => values[category[1]],
    ),
  }));
  expect(SETTINGS_NAV_GROUPS).toEqual(groups);
});

test("every backend category is reachable and localized in frontend navigation", () => {
  const source = readRepoFile("src/kernel/schemas/setting.py");
  const enumSource = source
    .split("class SettingCategory")[1]
    .split("class JsonSchemaField")[0];
  const categories = [...enumSource.matchAll(/= "([a-z0-9_]+)"/g)].map(
    (match) => match[1],
  );
  expect([...CATEGORY_ORDER].sort()).toEqual(categories.sort());
  for (const locale of locales) {
    const data = JSON.parse(
      readFileSync(resolve(localeDir, `${locale}.json`), "utf8"),
    );
    for (const category of categories)
      expect(data.categories[category], `${locale}: ${category}`).toBeTruthy();
  }
});

test("settings navigation labels and group descriptions exist in every locale", () => {
  for (const locale of locales) {
    const data = JSON.parse(
      readFileSync(resolve(localeDir, `${locale}.json`), "utf8"),
    );
    const navigation = data.settings.navigation;
    expect(navigation, locale).toBeDefined();
    for (const key of [
      "browse",
      "subtitle",
      "searchPlaceholder",
      "searchResults",
      "allCategories",
      "resultCount",
      "clearSearch",
      "subcategory",
      "allSubcategories",
      "saveHint",
    ]) {
      expect(navigation[key], `${locale}: ${key}`).toBeTruthy();
    }
    for (const { id } of SETTINGS_NAV_GROUPS) {
      expect(navigation.groups[id]).toBeTruthy();
      expect(navigation.descriptions[id]).toBeTruthy();
    }
  }
});

test("every settingDesc key referenced by backend definitions exists in all five locales", () => {
  for (const loc of locales) {
    const data = JSON.parse(
      readFileSync(resolve(localeDir, `${loc}.json`), "utf8"),
    ) as { settingDesc: Record<string, string> };
    const missing = [...descKeys].filter((k) => !data.settingDesc?.[k]);
    expect(missing, `${loc} missing settingDesc: ${missing.join(",")}`).toEqual(
      [],
    );
  }
});

test("every settings subcategory has a localized label in all five locales", () => {
  for (const loc of locales) {
    const data = JSON.parse(
      readFileSync(resolve(localeDir, `${loc}.json`), "utf8"),
    ) as { subcategories: Record<string, string> };
    const missing = [...subcats].filter((k) => !data.subcategories?.[k]);
    expect(
      missing,
      `${loc} missing subcategories: ${missing.join(",")}`,
    ).toEqual([]);
  }
});

test("settingsPanelLabels map covers every subcategory used by backend definitions", () => {
  const source = readRepoFile(
    "frontend/src/components/panels/settingsPanelLabels.ts",
  );
  for (const sub of subcats) {
    expect(
      source,
      `subcategories.${sub} missing from SUBCATEGORY_LABELS map`,
    ).toMatch(new RegExp(`${sub}: t\\("subcategories\\.${sub}"\\)`));
  }
});
