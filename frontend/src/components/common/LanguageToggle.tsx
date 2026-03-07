import { useState, useRef, useEffect, useCallback } from "react";
import { useTranslation } from "react-i18next";
import { Languages, Check } from "lucide-react";

const LANGUAGES = [
  { code: "en", name: "English", nativeName: "English" },
  { code: "zh", name: "Chinese", nativeName: "中文" },
  { code: "ja", name: "Japanese", nativeName: "日本語" },
  { code: "ko", name: "Korean", nativeName: "한국어" },
];

export function LanguageToggle() {
  const { i18n, t } = useTranslation();
  const [isOpen, setIsOpen] = useState(false);
  const dropdownRef = useRef<HTMLDivElement>(null);

  const selectLanguage = useCallback(
    (code: string) => {
      i18n.changeLanguage(code);
      localStorage.setItem("language", code);
      setIsOpen(false);
    },
    [i18n],
  );

  // Close dropdown when clicking outside
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (
        dropdownRef.current &&
        !dropdownRef.current.contains(event.target as Node)
      ) {
        setIsOpen(false);
      }
    };

    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  // Handle keyboard navigation
  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape" && isOpen) {
        setIsOpen(false);
      }
    };

    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [isOpen]);

  return (
    <div className="relative" ref={dropdownRef}>
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="flex h-8 w-8 items-center justify-center rounded-lg text-gray-600 hover:bg-gray-100 dark:text-stone-300 dark:hover:bg-stone-800 transition-colors"
        title={t("settings.title")}
        aria-label={t("settings.title")}
        aria-expanded={isOpen}
        aria-haspopup="true"
      >
        <Languages size={20} />
      </button>

      {isOpen && (
        <div
          className="absolute right-0 mt-2 w-40 rounded-lg bg-white dark:bg-stone-800 shadow-lg border border-gray-200 dark:border-stone-700 py-1 z-50"
          role="menu"
        >
          {LANGUAGES.map((lang) => (
            <button
              key={lang.code}
              onClick={() => selectLanguage(lang.code)}
              className="w-full px-4 py-2 text-left text-sm hover:bg-gray-100 dark:hover:bg-stone-700 flex items-center justify-between text-gray-700 dark:text-stone-200"
              role="menuitem"
              aria-selected={i18n.language === lang.code}
            >
              <span>{lang.nativeName}</span>
              {i18n.language === lang.code && (
                <Check size={16} className="text-blue-500" />
              )}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
