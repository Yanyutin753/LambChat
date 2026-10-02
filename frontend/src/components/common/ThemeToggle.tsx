import { Sun, Moon, Coffee, AlertCircle } from "lucide-react";
import { LoadingSpinner } from "./LoadingSpinner";
import { useTranslation } from "react-i18next";
import { useTheme } from "../../contexts/ThemeContext";
import type { Theme } from "../../utils/themeDom";

interface ThemeToggleProps {
  className?: string;
}

/** 当前主题下点击后将切换到的目标主题 */
const NEXT_THEME_LABEL_KEY: Record<Theme, string> = {
  light: "theme.switchToDark",
  dark: "theme.switchToSepia",
  sepia: "theme.switchToLight",
};

export function ThemeToggle({ className }: ThemeToggleProps) {
  const { theme, toggleTheme, appearanceState, retryAppearance } = useTheme();
  const { t } = useTranslation();
  const saving = appearanceState === "saving";
  const failed = appearanceState === "error";
  const label = failed
    ? `${t("common.retry")}: ${t("profile.theme")}`
    : saving
      ? t("common.saving")
      : `${t(NEXT_THEME_LABEL_KEY[theme])} · ${t("theme.cycleShortcut")}`;

  return (
    <button
      type="button"
      onClick={failed ? retryAppearance : toggleTheme}
      disabled={saving}
      aria-busy={saving || undefined}
      aria-label={label}
      aria-description={failed ? t("profile.preferenceSyncFailed") : undefined}
      className={
        className ??
        "flex h-8 w-8 items-center justify-center rounded-lg text-stone-600 hover:bg-stone-100 dark:text-stone-300 dark:hover:bg-stone-800 transition-colors"
      }
      title={label}
    >
      {saving ? (
        <LoadingSpinner size="sm" />
      ) : failed ? (
        <AlertCircle size={20} className="text-theme-error" />
      ) : theme === "light" ? (
        <Moon size={20} className="text-[var(--theme-text-secondary)]" />
      ) : theme === "dark" ? (
        <Coffee size={20} className="text-amber-400" />
      ) : (
        <Sun size={20} className="text-amber-500" />
      )}
    </button>
  );
}
