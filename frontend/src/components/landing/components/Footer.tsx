import { useTranslation } from "react-i18next";
import { APP_NAME, GITHUB_URL } from "../../../constants";
import { TECH_STACK } from "../data";
import { NAV_ITEMS } from "../constants";
import { GitHubIcon } from "./Icons";

interface FooterProps {
  onScrollToSection: (id: string) => void;
}

export function Footer({ onScrollToSection }: FooterProps) {
  const { t } = useTranslation();

  return (
    <footer className="blog-mesh-footer relative border-t border-stone-200/50 dark:border-stone-800/30 bg-stone-50/30 dark:bg-stone-900/15">
      {/* Top accent */}
      <div className="absolute top-0 left-1/2 -translate-x-1/2 w-32 h-px bg-gradient-to-r from-transparent via-amber-400/50 to-transparent dark:via-amber-500/25" />

      <div className="max-w-6xl xl:max-w-7xl mx-auto px-5 sm:px-6 pt-24 sm:pt-28 pb-10 sm:pb-12">
        <div className="grid grid-cols-1 sm:grid-cols-12 gap-14 sm:gap-8 mb-16 sm:mb-20">
          {/* Brand */}
          <div className="sm:col-span-5">
            <div className="flex items-center gap-2.5 mb-5">
              <img
                src="/icons/icon.svg"
                alt=""
                className="w-5 h-5 rounded-md"
              />
              <span className="text-sm font-bold tracking-tight text-stone-900 dark:text-stone-100 font-serif">
                {APP_NAME}
              </span>
            </div>
            <p className="text-sm text-stone-400 dark:text-stone-500 leading-[1.75] mb-7 max-w-xs">
              {t("landing.footerTagline")}
            </p>
            <a
              href={GITHUB_URL}
              target="_blank"
              rel="noopener noreferrer"
              className="blog-btn-ghost inline-flex items-center gap-2 rounded-full border border-stone-200/80 dark:border-stone-700/50 px-4 py-2 text-xs font-medium text-stone-500 dark:text-stone-400 hover:text-stone-900 dark:hover:text-stone-50 transition-all duration-200"
            >
              <GitHubIcon className="h-3.5 w-3.5" />
              GitHub
            </a>
          </div>

          {/* Link columns */}
          <div className="sm:col-span-7 grid grid-cols-3 gap-10 sm:gap-12">
            <div>
              <h4 className="text-[10px] font-bold tracking-[0.14em] uppercase text-stone-400 dark:text-stone-500 mb-5">
                {t("landing.coreFeatures")}
              </h4>
              <ul className="space-y-3">
                {NAV_ITEMS.map((item) => (
                  <li key={item.id}>
                    <button
                      onClick={() => onScrollToSection(item.id)}
                      className="text-[13px] text-stone-400 dark:text-stone-500 hover:text-stone-900 dark:hover:text-stone-50 transition-colors duration-200"
                    >
                      {t(`landing.${item.labelKey}`)}
                    </button>
                  </li>
                ))}
                <li>
                  <button
                    onClick={() => onScrollToSection("responsive")}
                    className="text-[13px] text-stone-400 dark:text-stone-500 hover:text-stone-900 dark:hover:text-stone-50 transition-colors duration-200"
                  >
                    {t("landing.responsiveDesign")}
                  </button>
                </li>
              </ul>
            </div>
            <div>
              <h4 className="text-[10px] font-bold tracking-[0.14em] uppercase text-stone-400 dark:text-stone-500 mb-5">
                Resources
              </h4>
              <ul className="space-y-3">
                <li>
                  <a
                    href={GITHUB_URL}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-[13px] text-stone-400 dark:text-stone-500 hover:text-stone-900 dark:hover:text-stone-50 transition-colors duration-200 inline-flex items-center gap-1.5"
                  >
                    <GitHubIcon className="h-3.5 w-3.5" /> GitHub
                  </a>
                </li>
                <li>
                  <a
                    href={GITHUB_URL}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-[13px] text-stone-400 dark:text-stone-500 hover:text-stone-900 dark:hover:text-stone-50 transition-colors duration-200"
                  >
                    MIT License
                  </a>
                </li>
              </ul>
            </div>
            <div>
              <h4 className="text-[10px] font-bold tracking-[0.14em] uppercase text-stone-400 dark:text-stone-500 mb-5">
                {t("landing.footerBuiltWith")}
              </h4>
              <div className="flex flex-col gap-2.5">
                {TECH_STACK.map((tech) => (
                  <span
                    key={tech.label}
                    className={`inline-flex items-center self-start rounded-full px-3 py-1 text-[11px] font-medium ${tech.color} border border-stone-100/80 dark:border-stone-700/30`}
                  >
                    {tech.label}
                  </span>
                ))}
              </div>
            </div>
          </div>
        </div>

        {/* Bottom */}
        <div className="pt-8 border-t border-stone-200/30 dark:border-stone-800/20 flex flex-col sm:flex-row items-center justify-between gap-3">
          <span className="text-xs text-stone-300 dark:text-stone-600 font-serif tracking-wide">
            &copy; {new Date().getFullYear()} {APP_NAME}
          </span>
          <div className="flex items-center gap-2.5 text-xs text-stone-300 dark:text-stone-600">
            <span>Open Source</span>
            <span className="w-1 h-1 rounded-full bg-stone-200 dark:bg-stone-700" />
            <span>MIT</span>
          </div>
        </div>
      </div>
    </footer>
  );
}
