import { useState, useRef, useEffect, useCallback } from "react";
import { useTranslation } from "react-i18next";
import { Languages, Check } from "lucide-react";
import { authApi } from "../../services/api";

const LANGUAGES = [
  { code: "en", name: "English", nativeName: "English" },
  { code: "zh", name: "Chinese", nativeName: "中文" },
  { code: "ja", name: "Japanese", nativeName: "日本語" },
  { code: "ko", name: "Korean", nativeName: "한국어" },
  { code: "ru", name: "Russian", nativeName: "Русский" },
];

interface LanguageToggleProps {
  className?: string;
}

export function LanguageToggle({ className }: LanguageToggleProps) {
  const { i18n, t } = useTranslation();
  const [isOpen, setIsOpen] = useState(false);
  const dropdownRef = useRef<HTMLDivElement>(null);

  const selectLanguage = useCallback(
    (code: string) => {
      i18n.changeLanguage(code);
      localStorage.setItem("language", code);
      setIsOpen(false);
      authApi.updateMetadata({ language: code }).catch(() => {});
    },
    [i18n],
  );

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
        className={
          className ??
          "flex h-8 w-8 items-center justify-center rounded-lg text-stone-600 hover:bg-stone-100 dark:text-stone-300 dark:hover:bg-stone-800 transition-colors"
        }
        title={t("common.language")}
        aria-label={t("common.language")}
        aria-expanded={isOpen}
        aria-haspopup="true"
      >
        <Languages size={20} />
      </button>

      {isOpen && (
        <div
          className="absolute right-0 mt-2 w-40 rounded-lg bg-white dark:bg-stone-800 shadow-lg border border-stone-200 dark:border-stone-700 py-1 z-50"
          role="menu"
        >
          {LANGUAGES.map((lang) => (
            <button
              key={lang.code}
              onClick={() => selectLanguage(lang.code)}
              className={`w-full px-4 py-2 text-left text-sm flex items-center justify-between transition-colors ${
                i18n.language === lang.code
                  ? "bg-stone-100 dark:bg-stone-700 text-stone-900 dark:text-stone-100"
                  : "text-stone-700 dark:text-stone-200 hover:bg-stone-50 dark:hover:bg-stone-700/50"
              }`}
              role="menuitem"
              aria-selected={i18n.language === lang.code}
            >
              <span>{lang.nativeName}</span>
              {i18n.language === lang.code && (
                <Check
                  size={16}
                  className="text-stone-700 dark:text-stone-200"
                />
              )}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
