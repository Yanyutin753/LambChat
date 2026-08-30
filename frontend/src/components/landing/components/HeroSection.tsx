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
    <section className={getHeroSectionClassName()}>
      {/* Atmospheric background */}
      <div
        className="pointer-events-none absolute inset-0 -z-10"
        aria-hidden="true"
      >
        <div className="absolute inset-0 blog-crosshatch" />
        <div className="blog-hero-glow-main absolute top-0 left-1/2 -translate-x-1/2 w-[900px] h-[600px] bg-[radial-gradient(ellipse_at_center,rgba(251,191,36,0.08)_0%,rgba(251,146,60,0.04)_40%,transparent_70%)] dark:bg-[radial-gradient(ellipse_at_center,rgba(251,191,36,0.06)_0%,rgba(251,146,60,0.03)_40%,transparent_70%)]" />
        <div className="blog-hero-glow-blue absolute top-[40%] left-[10%] w-[400px] h-[400px] bg-[radial-gradient(circle,rgba(56,189,248,0.06)_0%,transparent_60%)] dark:bg-[radial-gradient(circle,rgba(56,189,248,0.04)_0%,transparent_60%)]" />
        <div className="blog-hero-glow-violet absolute bottom-[10%] right-[15%] w-[300px] h-[300px] bg-[radial-gradient(circle,rgba(168,85,247,0.04)_0%,transparent_60%)] dark:bg-[radial-gradient(circle,rgba(168,85,247,0.03)_0%,transparent_60%)]" />
        {/* Floating light orbs */}
        <div className="blog-light-orb blog-light-orb-amber absolute top-[20%] left-[5%] opacity-60" />
        <div className="blog-light-orb blog-light-orb-blue absolute top-[55%] right-[3%] opacity-40" />
        <div className="blog-light-orb blog-light-orb-violet absolute bottom-[15%] left-[30%] opacity-30" />
      </div>

      {/* Floating decorative elements */}
      <div
        className="blog-hero-float absolute top-28 left-[7%] blog-float-line opacity-40"
        aria-hidden="true"
      />
      <div
        className="blog-hero-float absolute top-36 right-[9%] blog-float-line-short opacity-30"
        aria-hidden="true"
      />
      <div
        className="blog-hero-float absolute top-[60%] right-[6%] blog-float-dot opacity-20"
        aria-hidden="true"
      />

      <div className="relative mx-auto w-full max-w-[22rem] sm:max-w-4xl lg:max-w-5xl xl:max-w-6xl">
        {/* Editorial tag */}
        <div
          data-reveal
          className="flex items-center justify-center gap-2.5 sm:gap-3 mb-8 sm:mb-12"
        >
          <span className="block w-6 sm:w-8 h-px bg-gradient-to-r from-transparent to-stone-300 dark:to-stone-600" />
          <span className="relative text-10 sm:text-xs font-semibold tracking-[0.16em] sm:tracking-[0.18em] uppercase text-stone-400 dark:text-stone-500">
            {t("landing.badge")}
            <span className="blog-pulse-dot absolute -top-1.5 -right-2.5 w-1.5 h-1.5 rounded-full bg-emerald-400" />
          </span>
          <span className="block w-6 sm:w-8 h-px bg-gradient-to-l from-transparent to-stone-300 dark:to-stone-600" />
        </div>

        {/* Title */}
        <h1
          data-reveal
          data-reveal-delay="1"
          className="blog-hero-title mb-7 flex justify-center text-stone-900 dark:text-stone-50 sm:mb-10"
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
          className="blog-prose text-15 sm:text-lg lg:text-xl text-stone-500 dark:text-stone-400 max-w-[20rem] sm:max-w-lg mx-auto leading-[1.8] sm:leading-[1.85] mb-11 sm:mb-16"
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
            className="blog-btn-primary min-h-12 w-full sm:w-auto group inline-flex items-center justify-center gap-2.5 rounded-full bg-stone-900 dark:bg-stone-50 px-8 py-3.5 sm:px-9 sm:py-4 text-sm font-semibold text-white dark:text-stone-900 transition-all duration-300 hover:-translate-y-0.5 hover:bg-stone-800 dark:hover:bg-white hover:shadow-xl hover:shadow-stone-900/12 dark:hover:shadow-stone-50/10 active:translate-y-0"
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
            className="blog-btn-ghost min-h-12 w-full sm:w-auto group inline-flex items-center justify-center gap-2.5 rounded-full border border-stone-200/80 dark:border-stone-700/50 bg-white/55 dark:bg-stone-800/35 px-8 py-3.5 sm:px-9 sm:py-4 text-sm font-medium text-stone-600 dark:text-stone-300 transition-all duration-300 hover:-translate-y-0.5 hover:border-stone-300 dark:hover:border-stone-600 hover:shadow-lg hover:shadow-stone-200/30 dark:hover:shadow-stone-900/30 active:translate-y-0"
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
            <span className="text-10 font-semibold tracking-[0.14em] uppercase text-stone-300 dark:text-stone-600">
              {t("landing.footerBuiltWith")}
            </span>
            {TECH_STACK.map((tech) => (
              <span
                key={tech.label}
                className={`blog-tech-pill inline-flex items-center rounded-full px-3 py-1 text-11 sm:text-xs font-medium ${tech.color} border border-stone-100/60 dark:border-stone-700/20`}
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
