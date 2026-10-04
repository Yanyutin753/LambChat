import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import { Download } from "lucide-react";
import { ThemeToggle } from "../../common/ThemeToggle";
import { LanguageToggle } from "../../common/LanguageToggle";
import { BrandWordmark } from "../../common/BrandWordmark";
import { BrandLogo } from "../../common/BrandLogo";
import { NAV_ITEMS } from "../constants";
import { CloseIcon, MenuIcon } from "./Icons";

interface NavbarProps {
  activeSection: string;
  scrolled: boolean;
  mobileMenuOpen: boolean;
  onToggleMobileMenu: () => void;
  onScrollToSection: (id: string) => void;
}

export function Navbar({
  activeSection,
  scrolled,
  mobileMenuOpen,
  onToggleMobileMenu,
  onScrollToSection,
}: NavbarProps) {
  const { t } = useTranslation();

  return (
    <nav
      style={{ top: "var(--titlebar-inset, 0px)" }}
      className={`safe-area-top fixed inset-x-0 z-50 bg-white/85 dark:bg-stone-950/85 border-b border-stone-100/60 dark:border-stone-800/40 transition-shadow duration-300 ${
        scrolled ? "blog-nav-scrolled" : ""
      }`}
    >
      <div className="max-w-full mx-auto px-4 sm:px-8 h-14 flex items-center justify-between">
        <Link
          to="/"
          aria-label="LambChat"
          className="public-brand-link flex items-center group gap-1.5"
        >
          <BrandLogo className="size-8 transition-transform duration-300 group-hover:scale-105" />
          <BrandWordmark
            decorative
            className="w-auto text-stone-900 dark:text-stone-100 h-8 max-[379px]:hidden"
          />
        </Link>

        {/* Desktop nav links */}
        <div className="public-nav-links hidden xl:flex items-center gap-0.5">
          {NAV_ITEMS.map((item) => (
            <button
              key={item.id}
              aria-current={activeSection === item.id ? "location" : undefined}
              onClick={() => onScrollToSection(item.id)}
              className={`landing-nav-pill px-3.5 py-1.5 rounded-lg text-13 font-medium transition-colors ${
                activeSection === item.id
                  ? "active text-stone-900 dark:text-stone-100"
                  : "text-theme-text-secondary dark:text-theme-text-secondary hover:text-theme-text-secondary dark:hover:text-stone-200"
              }`}
            >
              {t(`landing.${item.labelKey}`)}
            </button>
          ))}
        </div>

        <div className="public-nav-actions flex items-center gap-1.5">
          <Link
            className="ui-button ui-icon-button ui-button--ghost !size-11"
            to="/download"
            aria-label={t("imageViewer.download")}
            title={t("imageViewer.download")}
          >
            <Download size={18} aria-hidden="true" />
          </Link>
          <LanguageToggle />
          <ThemeToggle />
          <button
            id="public-menu-toggle"
            aria-expanded={mobileMenuOpen}
            aria-controls="public-mobile-menu"
            className="xl:hidden ml-0.5 flex h-8 w-8 items-center justify-center rounded-lg text-theme-text-secondary hover:bg-stone-100 dark:text-theme-text-tertiary dark:hover:bg-stone-800 transition-colors"
            onClick={onToggleMobileMenu}
            aria-label={t("landing.toggleMenu")}
          >
            {mobileMenuOpen ? <CloseIcon /> : <MenuIcon />}
          </button>
        </div>
      </div>
    </nav>
  );
}
