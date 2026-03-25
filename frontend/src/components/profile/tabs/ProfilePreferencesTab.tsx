import { useTranslation } from "react-i18next";
import { Languages, Sun, Moon } from "lucide-react";
import { useTheme } from "../../../contexts/ThemeContext";
import { authApi } from "../../../services/api";

const LANGUAGES = [
  { code: "en", nativeName: "English" },
  { code: "zh", nativeName: "中文" },
  { code: "ja", nativeName: "日本語" },
  { code: "ko", nativeName: "한국어" },
  { code: "ru", nativeName: "Русский" },
];

export function ProfilePreferencesTab() {
  const { t, i18n } = useTranslation();
  const { theme, setTheme } = useTheme();

  const handleLanguageChange = (code: string) => {
    i18n.changeLanguage(code);
    localStorage.setItem("language", code);
    authApi.updateMetadata({ language: code }).catch(() => {});
  };

  const handleThemeChange = (newTheme: "light" | "dark") => {
    setTheme(newTheme);
    authApi.updateMetadata({ theme: newTheme }).catch(() => {});
  };

  return (
    <div className="space-y-3">
      {/* Language */}
      <div className="rounded-xl bg-stone-50 dark:bg-stone-700/50 p-3.5 sm:p-4">
        <div className="flex items-center gap-2 mb-3">
          <Languages size={16} className="text-stone-500 dark:text-stone-400" />
          <h4 className="font-medium text-sm text-stone-900 dark:text-stone-100">
            {t("profile.language")}
          </h4>
        </div>
        <div className="flex flex-wrap gap-2">
          {LANGUAGES.map((lang) => (
            <button
              key={lang.code}
              onClick={() => handleLanguageChange(lang.code)}
              className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${
                i18n.language === lang.code
                  ? "bg-amber-100 dark:bg-amber-900/30 text-amber-700 dark:text-amber-300 border border-amber-200 dark:border-amber-800"
                  : "bg-white dark:bg-stone-600/50 text-stone-600 dark:text-stone-300 border border-stone-200 dark:border-stone-600 hover:bg-stone-100 dark:hover:bg-stone-600"
              }`}
            >
              {lang.nativeName}
            </button>
          ))}
        </div>
      </div>

      {/* Theme */}
      <div className="rounded-xl bg-stone-50 dark:bg-stone-700/50 p-3.5 sm:p-4">
        <div className="flex items-center gap-2 mb-3">
          {theme === "dark" ? (
            <Moon size={16} className="text-stone-500 dark:text-stone-400" />
          ) : (
            <Sun size={16} className="text-stone-500 dark:text-stone-400" />
          )}
          <h4 className="font-medium text-sm text-stone-900 dark:text-stone-100">
            {t("profile.theme")}
          </h4>
        </div>
        <div className="flex gap-2">
          <button
            onClick={() => handleThemeChange("light")}
            className={`flex-1 flex items-center justify-center gap-2 px-3 py-2 rounded-lg text-xs font-medium transition-colors ${
              theme === "light"
                ? "bg-amber-100 dark:bg-amber-900/30 text-amber-700 dark:text-amber-300 border border-amber-200 dark:border-amber-800"
                : "bg-white dark:bg-stone-600/50 text-stone-600 dark:text-stone-300 border border-stone-200 dark:border-stone-600 hover:bg-stone-100 dark:hover:bg-stone-600"
            }`}
          >
            <Sun size={14} />
            {t("profile.lightTheme")}
          </button>
          <button
            onClick={() => handleThemeChange("dark")}
            className={`flex-1 flex items-center justify-center gap-2 px-3 py-2 rounded-lg text-xs font-medium transition-colors ${
              theme === "dark"
                ? "bg-amber-100 dark:bg-amber-900/30 text-amber-700 dark:text-amber-300 border border-amber-200 dark:border-amber-800"
                : "bg-white dark:bg-stone-600/50 text-stone-600 dark:text-stone-300 border border-stone-200 dark:border-stone-600 hover:bg-stone-100 dark:hover:bg-stone-600"
            }`}
          >
            <Moon size={14} />
            {t("profile.darkTheme")}
          </button>
        </div>
      </div>
    </div>
  );
}
