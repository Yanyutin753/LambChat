import { Sun, Moon } from "lucide-react";
import { useTranslation } from "react-i18next";
import { useTheme } from "../../contexts/ThemeContext";

export function ThemeToggle() {
  const { theme, toggleTheme } = useTheme();
  const { t } = useTranslation();

  return (
    <button
      onClick={toggleTheme}
      className="flex h-8 w-8 items-center justify-center rounded-lg text-stone-600 hover:bg-stone-100 dark:text-stone-300 dark:hover:bg-stone-800 transition-colors"
      title={
        theme === "light" ? t("theme.switchToDark") : t("theme.switchToLight")
      }
    >
      {theme === "light" ? (
        <Moon size={20} className="text-[var(--theme-text-secondary)]" />
      ) : (
        <Sun size={20} className="text-amber-400" />
      )}
    </button>
  );
}
