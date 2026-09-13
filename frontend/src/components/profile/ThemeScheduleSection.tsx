import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Clock } from "lucide-react";

import { useTheme } from "../../contexts/ThemeContext";
import { SelectRow } from "./SelectRow";
import {
  currentLocalMinutes,
  resolveScheduledTheme,
  type ThemeSchedule,
} from "../../utils/themeDom";

const NIGHT_THEME_OPTIONS: { key: "dark" | "sepia"; labelKey: string }[] = [
  { key: "dark", labelKey: "profile.darkTheme" },
  { key: "sepia", labelKey: "profile.sepiaTheme" },
];

const DEFAULT_SCHEDULE: ThemeSchedule = {
  enabled: false,
  start: "22:00",
  end: "07:00",
  nightTheme: "sepia",
};

/** 按时段自动切换主题的配置分区；手动切主题由 ThemeProvider 负责退出自动模式 */
export function ThemeScheduleSection() {
  const { t } = useTranslation();
  const { themeSchedule, setThemeSchedule } = useTheme();
  const [openDropdown, setOpenDropdown] = useState<string | null>(null);

  const schedule = themeSchedule ?? DEFAULT_SCHEDULE;
  const update = (patch: Partial<ThemeSchedule>) =>
    setThemeSchedule({ ...schedule, ...patch });

  const previewTheme = resolveScheduledTheme(currentLocalMinutes(), schedule);

  return (
    <>
      <button
        onClick={() => update({ enabled: !schedule.enabled })}
        className="flex w-full items-center justify-between py-3 first:pt-0 last:pb-0 text-left"
      >
        <span className="text-14 text-theme-text dark:text-stone-200">
          {t("profile.themeScheduleToggle")}
        </span>
        <span
          className={`relative h-5 w-9 rounded-full transition-colors ${
            schedule.enabled
              ? "bg-amber-500"
              : "bg-theme-border-hover dark:bg-stone-600"
          }`}
          role="switch"
          aria-checked={schedule.enabled}
          aria-label={t("profile.themeScheduleToggle")}
        >
          <span
            className={`absolute top-0.5 h-4 w-4 rounded-full bg-theme-toggle-knob transition-all ${
              schedule.enabled ? "left-[1.15rem]" : "left-0.5"
            }`}
          />
        </span>
      </button>

      {schedule.enabled && (
        <div className="space-y-1 pb-3">
          <div className="flex items-center gap-1.5 pb-1 text-12 text-theme-text-secondary dark:text-stone-400">
            <Clock size={12} className="text-theme-text-tertiary" />
            <span>
              {t("profile.themeSchedulePreview", {
                theme: t(
                  previewTheme === "dark"
                    ? "profile.darkTheme"
                    : previewTheme === "sepia"
                      ? "profile.sepiaTheme"
                      : "profile.lightTheme",
                ),
              })}
            </span>
          </div>
          <label className="flex w-full items-center justify-between py-2 text-left">
            <span className="text-14 text-theme-text dark:text-stone-200">
              {t("profile.themeScheduleStart")}
            </span>
            <input
              type="time"
              value={schedule.start}
              onChange={(e) => update({ start: e.target.value })}
              className="rounded-lg border border-theme-border bg-theme-bg-card px-2 py-1 text-13 text-theme-text dark:border-stone-600 dark:bg-stone-800 dark:text-stone-200"
            />
          </label>
          <label className="flex w-full items-center justify-between py-2 text-left">
            <span className="text-14 text-theme-text dark:text-stone-200">
              {t("profile.themeScheduleEnd")}
            </span>
            <input
              type="time"
              value={schedule.end}
              onChange={(e) => update({ end: e.target.value })}
              className="rounded-lg border border-theme-border bg-theme-bg-card px-2 py-1 text-13 text-theme-text dark:border-stone-600 dark:bg-stone-800 dark:text-stone-200"
            />
          </label>
          <SelectRow
            label={t("profile.themeScheduleNightTheme")}
            value={schedule.nightTheme}
            options={NIGHT_THEME_OPTIONS}
            open={openDropdown === "nightTheme"}
            onToggle={() =>
              setOpenDropdown((prev) => (prev === "nightTheme" ? null : "nightTheme"))
            }
            onSelect={(key) => {
              update({ nightTheme: key });
              setOpenDropdown(null);
            }}
          />
        </div>
      )}
    </>
  );
}

export default ThemeScheduleSection;
