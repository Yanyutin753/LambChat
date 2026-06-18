import { CORE_SETTINGS_SECTIONS } from "../../extensions/coreContributions";
import type { SettingCategory, SettingType } from "../../types";

export const CATEGORY_ORDER: SettingCategory[] = CORE_SETTINGS_SECTIONS.map(
  (section) => section.category,
);

export const TYPE_COLORS: Record<SettingType, string> = {
  string: "bg-stone-100 text-stone-700 dark:bg-stone-800 dark:text-stone-300",
  text: "bg-cyan-100 text-cyan-700 dark:bg-cyan-900/50 dark:text-cyan-300",
  number:
    "bg-green-100 text-green-700 dark:bg-green-900/50 dark:text-green-300",
  boolean:
    "bg-purple-100 text-purple-700 dark:bg-purple-900/50 dark:text-purple-300",
  json: "bg-orange-100 text-orange-700 dark:bg-orange-900/50 dark:text-orange-300",
  select: "bg-blue-100 text-blue-700 dark:bg-blue-900/50 dark:text-blue-300",
};

export const MODEL_CONFIG_SETTING_KEYS = new Set([
  "DEFAULT_MODEL_ID",
  "SESSION_TITLE_MODEL",
  "NATIVE_MEMORY_MODEL",
  "NATIVE_MEMORY_COMPACTION_MODEL_ID",
]);
