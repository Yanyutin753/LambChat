import { useTranslation } from "react-i18next";
import { APP_NAME, GITHUB_URL } from "../../../constants";
import { BrandWordmark } from "../../common/BrandWordmark";
import { TECH_STACK } from "../data";
import { ArrowIcon, GitHubIcon } from "./Icons";
import { getHeroSectionClassName } from "./landingHeroLayout";

interface HeroSectionProps {
  onLogin: () => void;
}

export function HeroSection({ onLogin }: HeroSectionProps) {
  const { t } = useTranslation();

  return (
    <section className={`${getHeroSectionClassName()} public-brand-hero`}>
      <div className="relative mx-auto w-full max-w-[22rem] sm:max-w-4xl lg:max-w-5xl xl:max-w-6xl">
        {/* Editorial tag */}
        <div
          data-reveal
          className="flex items-center justify-center gap-2.5 sm:gap-3 mb-8 sm:mb-12"
        >
          <span className="block w-6 sm:w-8 h-px bg-gradient-to-r from-transparent to-stone-300 dark:to-stone-600" />
          <span className="relative text-10 sm:text-12 font-semibold tracking-[0.16em] sm:tracking-[0.18em] uppercase text-theme-text-secondary dark:text-theme-text-secondary">
            {t("landing.badge")}
            <span className="blog-pulse-dot absolute -top-1.5 -right-2.5 w-1.5 h-1.5 rounded-full bg-emerald-400" />
          </span>
          <span className="block w-6 sm:w-8 h-px bg-gradient-to-l from-transparent to-stone-300 dark:to-stone-600" />
        </div>

        {/* Title */}
        <h1
          data-reveal
          data-reveal-delay="1"
          className="font-serif blog-hero-title mb-7 flex justify-center text-stone-900 dark:text-stone-50 sm:mb-10"
        >
          <BrandWordmark
            title={APP_NAME}
            className="h-auto w-[min(88vw,22rem)] sm:w-[36rem] md:w-[42rem] lg:w-[46rem]"
          />
        </h1>

        {/* Description */}
        <p
          data-reveal
          data-reveal-delay="3"
          className="blog-prose text-15 sm:text-18 lg:text-20 text-theme-text-secondary dark:text-theme-text-secondary max-w-[20rem] sm:max-w-lg mx-auto leading-[1.8] sm:leading-[1.85] mb-11 sm:mb-16"
        >
          {t("landing.heroDescription")}
        </p>

        {/* CTAs */}
        <div
          data-reveal
          data-reveal-delay="4"
          className="flex flex-col sm:flex-row items-center justify-center gap-3 sm:gap-4 max-w-[19rem] sm:max-w-none mx-auto"
        >
          <button
            onClick={onLogin}
            className="blog-btn-primary public-action public-action-primary group"
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
            className="blog-btn-ghost public-action public-action-secondary group"
          >
            <GitHubIcon />
            {t("landing.viewOnGitHub")}
          </a>
        </div>

        {/* Tech stack */}
        <div
          data-reveal
          data-reveal-delay="6"
          className="mt-12 sm:mt-24 pt-6 sm:pt-8 border-t border-stone-200/40 dark:border-stone-800/30"
        >
          <div className="flex flex-wrap items-center justify-center gap-x-3 gap-y-2 sm:gap-x-5 sm:gap-y-2.5">
            <span className="text-10 font-semibold tracking-[0.14em] uppercase text-theme-text-tertiary dark:text-theme-text-secondary">
              {t("landing.footerBuiltWith")}
            </span>
            {TECH_STACK.map((tech) => (
              <span
                key={tech.label}
                className={`blog-tech-pill inline-flex items-center rounded-full px-3 py-1 text-11 sm:text-12 font-medium text-theme-text-secondary border border-stone-100/60 dark:border-stone-700/20`}
              >
                {tech.label}
              </span>
            ))}
          </div>
        </div>
      </div>
      <img
        className="public-brand-art"
        src="/images/illustrations/auth-brand-workspace.webp"
        alt=""
        aria-hidden="true"
        fetchPriority="high"
      />
    </section>
  );
}
