import { useTranslation } from "react-i18next";
import { GITHUB_URL } from "../../../constants";
import { ArrowIcon, GitHubIcon } from "./Icons";

interface CTASectionProps {
  onLogin: () => void;
}

export function CTASection({ onLogin }: CTASectionProps) {
  const { t } = useTranslation();

  return (
    <section className="blog-mesh-cta blog-cta-ambient py-20 sm:py-28 lg:py-36 relative overflow-hidden">
      {/* Ambient glow */}
      <div className="absolute inset-0 pointer-events-none" aria-hidden="true">
        <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[700px] h-[400px] bg-[radial-gradient(ellipse,rgba(251,191,36,0.05)_0%,rgba(232,121,249,0.02)_40%,transparent_65%)] dark:bg-[radial-gradient(ellipse,rgba(251,191,36,0.04)_0%,rgba(232,121,249,0.015)_40%,transparent_65%)]" />
      </div>

      <div className="relative max-w-2xl lg:max-w-3xl mx-auto px-5 sm:px-6 text-center">
        {/* Ornamental top */}
        <div
          data-reveal
          className="flex items-center justify-center gap-3 mb-14 sm:mb-16"
        >
          <div className="w-20 sm:w-28 h-px bg-gradient-to-r from-transparent to-stone-300/50 dark:to-stone-600/30" />
          <div className="blog-ornament-diamond" />
          <div className="w-20 sm:w-28 h-px bg-gradient-to-l from-transparent to-stone-300/50 dark:to-stone-600/30" />
        </div>

        <h2
          data-reveal
          className="text-[1.65rem] sm:text-3xl lg:text-[2.2rem] font-extrabold font-serif tracking-[-0.025em] text-stone-900 dark:text-stone-50 mb-5 sm:mb-6 leading-[1.15]"
        >
          {t("landing.ctaTitle")}
        </h2>
        <p
          data-reveal
          data-reveal-delay="1"
          className="blog-prose text-stone-400 dark:text-stone-500 mb-12 sm:mb-14 text-sm sm:text-[15px] max-w-md mx-auto leading-[1.8] px-2"
        >
          {t("landing.ctaDescription")}
        </p>
        <div
          data-reveal
          data-reveal-delay="2"
          className="flex flex-col sm:flex-row items-center justify-center gap-3.5 sm:gap-4 max-w-sm sm:max-w-none mx-auto"
        >
          <button
            onClick={onLogin}
            className="blog-btn-primary w-full sm:w-auto group inline-flex items-center justify-center gap-2.5 rounded-full bg-stone-900 dark:bg-stone-50 px-8 py-4 sm:px-9 sm:py-4 text-sm font-semibold text-white dark:text-stone-900 transition-all duration-300 hover:-translate-y-0.5 hover:bg-stone-800 dark:hover:bg-white hover:shadow-xl hover:shadow-stone-900/12 dark:hover:shadow-stone-50/10 active:translate-y-0"
          >
            {t("landing.getStarted")}
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
      </div>
    </section>
  );
}
