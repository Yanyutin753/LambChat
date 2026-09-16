import type {
  SettingCategory,
  SettingItem,
  SettingsNavigationGroup,
} from "../../types";
import type { VisibleCategory } from "./settingsPanelGrouping";

export const SETTINGS_NAV_GROUPS: {
  id: string;
  categories: SettingCategory[];
}[] = [
  { id: "experience", categories: ["frontend", "session"] },
  { id: "intelligence", categories: ["agent", "llm", "scheduled_task"] },
  {
    id: "memory",
    categories: [
      "memory",
      "memory_embedding",
      "memory_search",
      "memory_storage",
    ],
  },
  {
    id: "capabilities",
    categories: [
      "tools",
      "skills",
      "sandbox",
      "file_upload",
      "document_parse",
      "audio_transcription",
    ],
  },
  {
    id: "access",
    categories: ["user", "security", "oauth", "captcha", "email"],
  },
  {
    id: "infrastructure",
    categories: [
      "mongodb",
      "redis",
      "checkpoint",
      "long_term_storage",
      "s3",
      "tracing",
    ],
  },
];

export function buildSettingsNavigation(
  visible: VisibleCategory[],
  navigation: SettingsNavigationGroup[] = SETTINGS_NAV_GROUPS,
) {
  return navigation
    .map(({ id, categories }) => ({
      id,
      categories: categories.flatMap((category) =>
        visible.filter((entry) => entry.category === category),
      ),
    }))
    .filter((group) => group.categories.length > 0);
}

export function filterSettings(
  items: SettingItem[],
  options: {
    query: string;
    includeAdmin?: boolean;
    category: SettingCategory;
    subcategory: string | null;
    isVisible: (setting: SettingItem) => boolean;
    translate: (key: string) => string;
    categoryLabels: Partial<Record<SettingCategory, string>>;
    subcategoryLabels: Record<string, string>;
  },
) {
  const query = options.query.trim().toLocaleLowerCase();
  return items.filter((setting) => {
    if (
      (!options.includeAdmin && setting.frontend_visible === false) ||
      !options.isVisible(setting)
    )
      return false;
    if (!query)
      return (
        setting.category === options.category &&
        (options.subcategory === null ||
          (setting.subcategory || "") === options.subcategory)
      );
    return [
      setting.key,
      setting.description,
      options.translate(setting.description),
      options.categoryLabels[setting.category],
      options.subcategoryLabels[setting.subcategory],
    ].some((value) => value?.toLocaleLowerCase().includes(query));
  });
}
