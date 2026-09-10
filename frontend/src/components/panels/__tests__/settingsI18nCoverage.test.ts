/** 设置面板 i18n 覆盖门禁：后端定义引用的 settingDesc.* 与全部 subcategory
 * 标签必须在五语齐全、且 settingsPanelLabels 映射表同步——缺一处直接挂 CI
 * （此前 18 个子类标签五语全缺，面板裸显英文 id）。 */

import { readFileSync, readdirSync } from "node:fs";
import { resolve, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const repoRoot = resolve(dirname(fileURLToPath(import.meta.url)), "../../../../..");
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
  for (const m of src.matchAll(/settingDesc\.([A-Z0-9_]+)/g)) descKeys.add(m[1]);
  for (const m of src.matchAll(/"subcategory":\s*"([a-z_]+)"/g)) subcats.add(m[1]);
}

const locales = ["zh", "en", "ja", "ko", "ru"] as const;

test("every settingDesc key referenced by backend definitions exists in all five locales", () => {
  for (const loc of locales) {
    const data = JSON.parse(
      readFileSync(resolve(localeDir, `${loc}.json`), "utf8"),
    ) as { settingDesc: Record<string, string> };
    const missing = [...descKeys].filter((k) => !data.settingDesc?.[k]);
    expect(missing, `${loc} missing settingDesc: ${missing.join(",")}`).toEqual([]);
  }
});

test("every settings subcategory has a localized label in all five locales", () => {
  for (const loc of locales) {
    const data = JSON.parse(
      readFileSync(resolve(localeDir, `${loc}.json`), "utf8"),
    ) as { subcategories: Record<string, string> };
    const missing = [...subcats].filter((k) => !data.subcategories?.[k]);
    expect(missing, `${loc} missing subcategories: ${missing.join(",")}`).toEqual([]);
  }
});

test("settingsPanelLabels map covers every subcategory used by backend definitions", () => {
  const source = readRepoFile("frontend/src/components/panels/settingsPanelLabels.ts");
  for (const sub of subcats) {
    expect(
      source,
      `subcategories.${sub} missing from SUBCATEGORY_LABELS map`,
    ).toMatch(new RegExp(`${sub}: t\\("subcategories\\.${sub}"\\)`));
  }
});
