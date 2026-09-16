import { useTranslation } from "react-i18next";
import type { SettingCategory, SettingsNavigationGroup } from "../../types";
import type { VisibleCategory } from "./settingsPanelGrouping";
import { buildSettingsNavigation } from "./settingsNavigation";

interface Props {
  categories: VisibleCategory[];
  activeCategory: SettingCategory;
  searching: boolean;
  labels: Partial<Record<SettingCategory, string>>;
  onSelect: (category: SettingCategory) => void;
  mobile?: boolean;
  navigation?: SettingsNavigationGroup[];
}

/** One taxonomy for desktop navigation and the compact mobile category picker. */
export function SettingsCategoryNav({
  categories,
  activeCategory,
  searching,
  labels,
  onSelect,
  mobile,
  navigation,
}: Props) {
  const { t } = useTranslation();
  const groups = buildSettingsNavigation(categories, navigation);
  if (mobile)
    return (
      <label className="mb-3 block sm:hidden">
        <span className="mb-1 block text-12 font-medium text-stone-500 dark:text-stone-400">
          {t("settings.navigation.browse")}
        </span>
        <select
          value={searching ? "" : activeCategory}
          onChange={(event) => onSelect(event.target.value as SettingCategory)}
          disabled={categories.length === 0}
          className="h-11 w-full rounded-lg border border-[var(--glass-border)] bg-[var(--theme-bg-card)] px-3 text-14 text-stone-900 focus-visible:outline focus-visible:outline-2 focus-visible:outline-[var(--theme-primary)] dark:text-stone-100"
        >
          {searching && (
            <option value="" disabled>
              {t("settings.navigation.searchResults")}
            </option>
          )}
          {groups.map((group) => (
            <optgroup
              key={group.id}
              label={t(`settings.navigation.groups.${group.id}`)}
            >
              {group.categories.map(({ category, count }) => (
                <option key={category} value={category}>
                  {labels[category]} · {count}
                </option>
              ))}
            </optgroup>
          ))}
        </select>
      </label>
    );

  return (
    <nav
      aria-label={t("settings.navigation.browse")}
      className="flex-1 space-y-5 overflow-y-auto px-3 py-3"
    >
      {groups.map((group) => (
        <div key={group.id}>
          <h3 className="mb-1 px-3 text-12 font-medium text-stone-500 dark:text-stone-400">
            {t(`settings.navigation.groups.${group.id}`)}
          </h3>
          <div className="space-y-0.5">
            {group.categories.map(({ category, count }) => {
              const active = !searching && category === activeCategory;
              return (
                <button
                  key={category}
                  type="button"
                  aria-current={active ? "page" : undefined}
                  onClick={() => onSelect(category)}
                  className={`flex min-h-10 w-full items-center justify-between gap-3 rounded-lg px-3 py-2 text-left text-14 focus-visible:outline focus-visible:outline-2 focus-visible:outline-[var(--theme-primary)] ${
                    active
                      ? "bg-[var(--glass-bg)] font-semibold text-[var(--theme-primary)]"
                      : "text-stone-600 hover:bg-[var(--glass-bg-subtle)] dark:text-stone-400"
                  }`}
                >
                  <span className="min-w-0 break-words">
                    {labels[category]}
                  </span>
                  <span className="text-12 tabular-nums text-stone-500 dark:text-stone-400">
                    {count}
                  </span>
                </button>
              );
            })}
          </div>
        </div>
      ))}
    </nav>
  );
}
