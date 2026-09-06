import { CATEGORY_ORDER } from "./SettingsPanel.constants";
import type { SettingCategory, SettingItem } from "../../types";

export interface VisibleCategory {
  category: SettingCategory;
  count: number;
}

/**
 * Categories that still expose visible settings; shared by the desktop
 * sidebar nav and the mobile chip strip so both stay in sync.
 */
export function buildVisibleCategories(
  settingsByCategory: Record<SettingCategory, SettingItem[]> | undefined,
  isSettingVisible: (setting: SettingItem) => boolean,
): VisibleCategory[] {
  return CATEGORY_ORDER.map((category) => {
    const count = (settingsByCategory?.[category] ?? []).filter(
      isSettingVisible,
    ).length;
    return { category, count };
  }).filter(({ count }) => count > 0);
}

export interface GroupedSettings {
  subcategory: string;
  label: string;
  settings: SettingItem[];
}

/**
 * Group filtered settings by category (when searching globally) or
 * subcategory (when browsing a single category).
 */
export function groupFilteredSettings(
  filteredSettings: SettingItem[],
  opts: {
    isGlobalSearch: boolean;
    categoryLabels: Record<SettingCategory, string>;
    subcategoryLabels: Record<string, string>;
  },
): GroupedSettings[] {
  const groups: GroupedSettings[] = [];
  const map = new Map<string, SettingItem[]>();

  for (const s of filteredSettings) {
    const key = opts.isGlobalSearch
      ? `__cat__:${s.category}`
      : s.subcategory || "";
    if (!map.has(key)) map.set(key, []);
    map.get(key)!.push(s);
  }
  for (const [key, items] of map) {
    if (opts.isGlobalSearch && key.startsWith("__cat__:")) {
      const catKey = key.slice("__cat__:".length) as SettingCategory;
      groups.push({
        subcategory: key,
        label: opts.categoryLabels[catKey] || catKey,
        settings: items,
      });
    } else {
      groups.push({
        subcategory: key,
        label: key ? opts.subcategoryLabels[key] || key : "",
        settings: items,
      });
    }
  }
  return groups;
}
