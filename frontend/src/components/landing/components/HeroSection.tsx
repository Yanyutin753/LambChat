import { useTranslation } from "react-i18next";
import { APP_NAME, GITHUB_URL } from "../../../constants";
import { TECH_STACK } from "../data";
import { ArrowIcon, GitHubIcon } from "./Icons";

interface HeroSectionProps {
  onLogin: () => void;
}

export function HeroSection({ onLogin }: HeroSectionProps) {
  const { t } = useTranslation();

  return (
    <section className="blog-hero relative flex flex-col items-center justify-center min-h-[100svh] px-5 sm:px-6 py-16 sm:py-20 overflow-hidden">
      {/* Atmospheric background */}
      <div
        className="pointer-events-none absolute inset-0 -z-10"
        aria-hidden="true"
      >
        <div className="absolute inset-0 blog-crosshatch" />
        <div className="absolute top-0 left-1/2 -translate-x-1/2 w-[900px] h-[600px] bg-[radial-gradient(ellipse_at_center,rgba(251,191,36,0.06)_0%,rgba(251,146,60,0.03)_40%,transparent_70%)] dark:bg-[radial-gradient(ellipse_at_center,rgba(251,191,36,0.04)_0%,rgba(251,146,60,0.02)_40%,transparent_70%)]" />
        <div className="absolute top-[40%] left-[10%] w-[400px] h-[400px] bg-[radial-gradient(circle,rgba(56,189,248,0.04)_0%,transparent_60%)] dark:bg-[radial-gradient(circle,rgba(56,189,248,0.03)_0%,transparent_60%)]" />
        <div className="absolute bottom-[10%] right-[15%] w-[300px] h-[300px] bg-[radial-gradient(circle,rgba(168,85,247,0.03)_0%,transparent_60%)] dark:bg-[radial-gradient(circle,rgba(168,85,247,0.02)_0%,transparent_60%)]" />
      </div>

      {/* Floating decorative elements */}
      <div
        className="absolute top-28 left-[7%] blog-float-line opacity-40"
        aria-hidden="true"
      />
      <div
        className="absolute top-36 right-[9%] blog-float-line-short opacity-30"
        aria-hidden="true"
      />
      <div
        className="absolute top-[60%] right-[6%] blog-float-dot opacity-20"
        aria-hidden="true"
      />

      <div className="relative max-w-2xl sm:max-w-3xl lg:max-w-4xl mx-auto text-center w-full">
        {/* Editorial tag */}
        <div
          data-reveal
          className="flex items-center justify-center gap-3 mb-10 sm:mb-12"
        >
          <span className="block w-8 h-px bg-gradient-to-r from-transparent to-stone-300 dark:to-stone-600" />
          <span className="relative text-[11px] sm:text-xs font-semibold tracking-[0.18em] uppercase text-stone-400 dark:text-stone-500">
            {t("landing.badge")}
            <span className="blog-pulse-dot absolute -top-1.5 -right-2.5 w-1.5 h-1.5 rounded-full bg-emerald-400" />
          </span>
          <span className="block w-8 h-px bg-gradient-to-l from-transparent to-stone-300 dark:to-stone-600" />
        </div>

        {/* Title */}
        <h1
          data-reveal
          data-reveal-delay="1"
          className="blog-hero-title text-[3.2rem] sm:text-7xl md:text-[5.5rem] lg:text-[6rem] font-extrabold font-serif tracking-[-0.035em] leading-[0.95] sm:leading-[0.92] mb-8 sm:mb-10 text-stone-900 dark:text-stone-50"
        >
          {APP_NAME}
        </h1>

        {/* Ornamental divider */}
        <div
          data-reveal
          data-reveal-delay="2"
          className="flex items-center justify-center gap-3 mb-10 sm:mb-12"
        >
          <div className="w-16 sm:w-24 h-px bg-gradient-to-r from-transparent to-stone-300/60 dark:to-stone-600/40" />
          <div className="blog-ornament-diamond" />
          <div className="w-16 sm:w-24 h-px bg-gradient-to-l from-transparent to-stone-300/60 dark:to-stone-600/40" />
        </div>

        {/* Description */}
        <p
          data-reveal
          data-reveal-delay="3"
          className="blog-prose text-base sm:text-lg lg:text-xl text-stone-500 dark:text-stone-400 max-w-lg mx-auto leading-[1.85] mb-14 sm:mb-16"
        >
          {t("landing.heroDescription")}
        </p>

        {/* CTAs */}
        <div
          data-reveal
          data-reveal-delay="4"
          className="flex flex-col sm:flex-row items-center justify-center gap-3.5 sm:gap-4 max-w-sm sm:max-w-none mx-auto"
        >
          <button
            onClick={onLogin}
            className="blog-btn-primary w-full sm:w-auto group inline-flex items-center justify-center gap-2.5 rounded-full bg-stone-900 dark:bg-stone-50 px-8 py-4 sm:px-9 sm:py-4 text-sm font-semibold text-white dark:text-stone-900 transition-all duration-300 hover:-translate-y-0.5 hover:bg-stone-800 dark:hover:bg-white hover:shadow-xl hover:shadow-stone-900/12 dark:hover:shadow-stone-50/10 active:translate-y-0"
          >
            {t("landing.startUsing")}
            <span className="transition-transform duration-300 group-hover:translate-x-0.5">
              <ArrowIcon />
            </span>
          </button>
          <a
            href={GITHUB_URL}
            target="_blank"
            rel="noopener noreferrer"
            className="blog-btn-ghost w-full sm:w-auto group inline-flex items-center justify-center gap-2.5 rounded-full border border-stone-200/80 dark:border-stone-700/50 bg-white/50 dark:bg-stone-800/30 px-8 py-4 sm:px-9 sm:py-4 text-sm font-medium text-stone-600 dark:text-stone-300 transition-all duration-300 hover:-translate-y-0.5 hover:border-stone-300 dark:hover:border-stone-600 hover:shadow-lg hover:shadow-stone-200/30 dark:hover:shadow-stone-900/30 active:translate-y-0"
          >
            <GitHubIcon />
            {t("landing.viewOnGitHub")}
          </a>
        </div>

        {/* Tech stack */}
        <div
          data-reveal
          data-reveal-delay="6"
          className="mt-16 sm:mt-24 pt-8 border-t border-stone-200/40 dark:border-stone-800/30"
        >
          <div className="flex flex-wrap items-center justify-center gap-x-5 gap-y-2.5">
            <span className="text-[10px] font-semibold tracking-[0.14em] uppercase text-stone-300 dark:text-stone-600">
              {t("landing.footerBuiltWith")}
            </span>
            {TECH_STACK.map((tech) => (
              <span
                key={tech.label}
                className={`blog-tech-pill inline-flex items-center rounded-full px-3 py-1 text-[11px] sm:text-xs font-medium ${tech.color} border border-stone-100/60 dark:border-stone-700/20`}
              >
                {tech.label}
              </span>
            ))}
          </div>
        </div>
      </div>
    </section>
  );
}
