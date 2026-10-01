import { useEffect, useRef } from "react";
import { Link } from "react-router-dom";
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
  const menuRef = useRef<HTMLElement>(null);

  useEffect(() => {
    menuRef.current?.querySelector<HTMLButtonElement>("button")?.focus();
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        onClose();
        document.getElementById("public-menu-toggle")?.focus();
      }
    };
    document.addEventListener("keydown", closeOnEscape);
    return () => document.removeEventListener("keydown", closeOnEscape);
  }, [onClose]);

  return (
    <div className="fixed inset-0 z-40 xl:hidden">
      <button
        type="button"
        aria-label={t("common.close")}
        className="absolute inset-0 bg-black/20 dark:bg-black/40"
        onClick={onClose}
      />
      <nav
        ref={menuRef}
        id="public-mobile-menu"
        aria-label={t("landing.toggleMenu")}
        className="landing-mobile-menu absolute top-[calc(3.5rem+var(--app-safe-area-top,0px))] inset-x-0 bg-white/90 dark:bg-stone-900/90 border-b border-stone-100/60 dark:border-stone-800/60 shadow-xl shadow-stone-200/30 dark:shadow-stone-900/50"
        onKeyDown={(event) => {
          if (event.key !== "Tab") return;
          const controls =
            event.currentTarget.querySelectorAll<HTMLElement>("button,a[href]");
          const first = controls[0],
            last = controls[controls.length - 1];
          if (event.shiftKey && document.activeElement === first) {
            event.preventDefault();
            last?.focus();
          } else if (!event.shiftKey && document.activeElement === last) {
            event.preventDefault();
            first?.focus();
          }
        }}
      >
        <div className="max-w-6xl mx-auto px-4 py-3">
          {NAV_ITEMS.map((item) => (
            <button
              key={item.id}
              onClick={() => onScrollToSection(item.id)}
              className={`w-full text-left px-4 py-3 rounded-xl text-14 font-medium transition-colors ${
                activeSection === item.id
                  ? "text-stone-900 dark:text-stone-100 bg-stone-100/80 dark:bg-stone-800/50"
                  : "text-theme-text-secondary dark:text-theme-text-secondary hover:text-theme-text-secondary dark:hover:text-stone-200 hover:bg-stone-50 dark:hover:bg-stone-800/20"
              }`}
            >
              {t(`landing.${item.labelKey}`)}
            </button>
          ))}
          <Link
            className="public-download-link block px-4 py-3"
            to="/download"
            onClick={onClose}
          >
            {t("imageViewer.download")}
          </Link>
        </div>
      </nav>
    </div>
  );
}
