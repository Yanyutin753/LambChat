import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";
import { ThemeToggle } from "../../common/ThemeToggle";
import { LanguageToggle } from "../../common/LanguageToggle";
import { APP_NAME } from "../../../constants";
import { NAV_ITEMS } from "../constants";
import { CloseIcon, MenuIcon } from "./Icons";

interface NavbarProps {
  activeSection: string;
  showNav: boolean;
  mobileMenuOpen: boolean;
  onToggleMobileMenu: () => void;
  onScrollToSection: (id: string) => void;
}

export function Navbar({
  activeSection,
  showNav,
  mobileMenuOpen,
  onToggleMobileMenu,
  onScrollToSection,
}: NavbarProps) {
  const { t } = useTranslation();
  const navigate = useNavigate();

  return (
    <nav className="fixed top-0 inset-x-0 z-50 bg-white/80 dark:bg-stone-950/80 border-b border-stone-100/60 dark:border-stone-800/40">
      <div className="max-wfull mx-auto px-5 sm:px-8 h-14 flex items-center justify-between">
        <div
          className="flex items-center gap-2.5 cursor-pointer group"
          onClick={() => navigate("/")}
        >
          <img
            src="/icons/icon.svg"
            alt=""
            className="w-6 h-6 sm:w-7 sm:h-7 rounded-lg transition-transform duration-300 group-hover:scale-105"
          />
          <span className="text-sm sm:text-[15px] font-bold tracking-tight text-stone-900 dark:text-stone-100 font-serif">
            {APP_NAME}
          </span>
        </div>

        {/* Desktop nav links */}
        <div
          className={`hidden md:flex items-center gap-0.5 absolute left-1/2 -translate-x-1/2 transition-all duration-500 ${
            showNav
              ? "opacity-100 translate-y-0"
              : "opacity-0 -translate-y-1.5 pointer-events-none"
          }`}
        >
          {NAV_ITEMS.map((item) => (
            <button
              key={item.id}
              onClick={() => onScrollToSection(item.id)}
              className={`landing-nav-pill px-3.5 py-1.5 rounded-lg text-[13px] font-medium transition-colors ${
                activeSection === item.id
                  ? "active text-stone-900 dark:text-stone-100"
                  : "text-stone-500 dark:text-stone-400 hover:text-stone-700 dark:hover:text-stone-200"
              }`}
            >
              {t(`landing.${item.labelKey}`)}
            </button>
          ))}
        </div>

        <div className="flex items-center gap-1.5">
          <LanguageToggle />
          <ThemeToggle />
          <button
            className="md:hidden ml-0.5 flex h-8 w-8 items-center justify-center rounded-lg text-stone-600 hover:bg-stone-100 dark:text-stone-300 dark:hover:bg-stone-800 transition-colors"
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
