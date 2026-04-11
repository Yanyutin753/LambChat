import { useTranslation } from "react-i18next";
import { NAV_ITEMS } from "../constants";

interface MobileMenuProps {
  activeSection: string;
  onClose: () => void;
  onScrollToSection: (id: string) => void;
}

export function MobileMenu({
  activeSection,
  onClose,
  onScrollToSection,
}: MobileMenuProps) {
  const { t } = useTranslation();

  return (
    <div className="fixed inset-0 z-40 md:hidden">
      <div
        className="absolute inset-0 bg-black/20 dark:bg-black/40"
        onClick={onClose}
      />
      <div className="landing-mobile-menu absolute top-14 inset-x-0 bg-white/95 dark:bg-stone-900/95 border-b border-stone-100 dark:border-stone-800/80 shadow-xl shadow-stone-200/30 dark:shadow-stone-900/50">
        <div className="max-w-6xl mx-auto px-4 py-3">
          {NAV_ITEMS.map((item) => (
            <button
              key={item.id}
              onClick={() => onScrollToSection(item.id)}
              className={`w-full text-left px-4 py-3 rounded-xl text-sm font-medium transition-colors ${
                activeSection === item.id
                  ? "text-stone-900 dark:text-stone-100 bg-stone-100/80 dark:bg-stone-800/50"
                  : "text-stone-500 dark:text-stone-400 hover:text-stone-700 dark:hover:text-stone-200 hover:bg-stone-50 dark:hover:bg-stone-800/20"
              }`}
            >
              {t(`landing.${item.labelKey}`)}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
