import { useId, useState } from "react";
import { ChevronDown } from "lucide-react";
import { Select } from "../common/ui/Select";
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
  const navigationId = useId();
  const [collapsedGroups, setCollapsedGroups] = useState<Set<string>>(new Set());
  const groups = buildSettingsNavigation(categories, navigation);
  if (mobile)
    return (
      <div className="settings-category-picker mb-3 block sm:hidden">
        <span className="mb-1 block text-12 font-medium text-stone-500 dark:text-stone-400">
          {t("settings.navigation.browse")}
        </span>
        <Select
          ariaLabel={t("settings.navigation.browse")}
          value={searching ? "" : activeCategory}
          onChange={(value) => onSelect(value as SettingCategory)}
          disabled={categories.length === 0}
          placeholder={
            searching ? t("settings.navigation.searchResults") : undefined
          }
          triggerClassName="min-h-11"
          options={groups.flatMap((group) =>
            group.categories.map(({ category, count }) => ({
              value: category,
              label: `${labels[category]} · ${count}`,
              group: t(`settings.navigation.groups.${group.id}`),
            })),
          )}
        />
      </div>
    );

  return (
    <nav
      aria-label={t("settings.navigation.browse")}
      className="flex-1 space-y-1 overflow-y-auto px-3 py-3"
    >
      {groups.map((group) => {
        const expanded = searching || !collapsedGroups.has(group.id);
        const contentId = `${navigationId}-${group.id}`;
        return (
          <div key={group.id}>
            <h3>
              <button
                type="button"
                aria-expanded={expanded}
                aria-controls={contentId}
                disabled={searching}
                onClick={() =>
                  setCollapsedGroups((previous) => {
                    const next = new Set(previous);
                    if (next.has(group.id)) next.delete(group.id);
                    else next.add(group.id);
                    return next;
                  })
                }
                className="flex min-h-8 w-full items-center gap-2 rounded-lg px-[9px] py-1 text-left text-14 font-medium [@media(pointer:coarse)]:min-h-11 text-stone-500 hover:bg-[var(--glass-bg-subtle)] focus-visible:outline focus-visible:outline-2 focus-visible:outline-[var(--theme-primary)] disabled:cursor-default dark:text-stone-400"
              >
                <span className="min-w-0 break-words">
                  {t(`settings.navigation.groups.${group.id}`)}
                </span>
                <ChevronDown
                  size={14}
                  aria-hidden="true"
                  className={`shrink-0 ${expanded ? "" : "-rotate-90"}`}
                />
              </button>
            </h3>
            <div id={contentId} hidden={!expanded} className="space-y-0.5">
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
        );
      })}
    </nav>
  );
}
