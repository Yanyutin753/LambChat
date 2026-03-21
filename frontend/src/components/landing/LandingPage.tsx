import { useEffect, useRef, useState, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { ThemeToggle } from "../common/ThemeToggle";
import { LanguageToggle } from "../common/LanguageToggle";
import { useAuth } from "../../hooks/useAuth";
import { APP_NAME } from "../../constants";
import {
  FEATURES,
  TECH_STACK,
  MAIN_SHOTS,
  MGMT_SHOTS,
  RESPONSIVE_SHOTS,
  STATS,
} from "./data";

/* ── Single shared IntersectionObserver ── */

function useScrollReveal() {
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const root = containerRef.current;
    if (!root) return;
    const els = root.querySelectorAll("[data-reveal], [data-reveal-scale]");
    if (!els.length) return;

    const obs = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (entry.isIntersecting) {
            entry.target.classList.add("revealed");
            obs.unobserve(entry.target);
          }
        }
      },
      { rootMargin: "0px 0px -30px 0px", threshold: 0.06 },
    );

    els.forEach((el) => obs.observe(el));
    return () => obs.disconnect();
  }, []);

  return containerRef;
}

/* ── Animated counter ── */

function AnimatedNumber({ value }: { value: string }) {
  const [display, setDisplay] = useState(value);
  const ref = useRef<HTMLSpanElement>(null);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;

    const numMatch = value.match(/^(\d+)/);
    if (!numMatch) {
      setDisplay(value);
      return;
    }

    const numVal = parseInt(numMatch[1]);
    const suffix = value.slice(numMatch[1].length);
    let start = 0;

    const obs = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          const duration = 1400;
          const step = (ts: number) => {
            if (!start) start = ts;
            const p = Math.min((ts - start) / duration, 1);
            const eased = 1 - Math.pow(1 - p, 4);
            setDisplay(Math.round(eased * numVal).toString() + suffix);
            if (p < 1) requestAnimationFrame(step);
          };
          requestAnimationFrame(step);
          obs.unobserve(el);
        }
      },
      { threshold: 0.5 },
    );

    obs.observe(el);
    return () => obs.disconnect();
  }, [value]);

  return <span ref={ref}>{display}</span>;
}

/* ── Inline icons ── */

function GitHubIcon({ className = "h-4 w-4" }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="currentColor">
      <path d="M12 0C5.37 0 0 5.37 0 12c0 5.31 3.435 9.795 8.205 11.385.6.105.825-.255.825-.57 0-.285-.015-1.23-.015-2.235-3.015.555-3.795-.735-4.035-1.41-.135-.345-.72-1.41-1.23-1.695-.42-.225-1.02-.78-.015-.795.945-.015 1.62.87 1.845 1.23 1.08 1.815 2.805 1.305 3.495.99.105-.78.42-1.305.765-1.605-2.67-.3-5.46-1.335-5.46-5.925 0-1.305.465-2.385 1.23-3.225-.12-.3-.54-1.53.12-3.18 0 0 1.005-.315 3.3 1.23.96-.27 1.98-.405 3-.405s2.04.135 3 .405c2.295-1.56 3.3-1.23 3.3-1.23.66 1.65.24 2.88.12 3.18.765.84 1.23 1.905 1.23 3.225 0 4.605-2.805 5.625-5.475 5.925.435.375.81 1.095.81 2.22 0 1.605-.015 2.895-.015 3.3 0 .315.225.69.825.57A12.02 12.02 0 0024 12c0-6.63-5.37-12-12-12z" />
    </svg>
  );
}

function ArrowIcon() {
  return (
    <svg
      className="w-3.5 h-3.5 sm:w-4 sm:h-4"
      viewBox="0 0 20 20"
      fill="currentColor"
    >
      <path
        fillRule="evenodd"
        d="M3 10a.75.75 0 01.75-.75h10.638L10.23 5.29a.75.75 0 111.04-1.08l5.5 5.25a.75.75 0 010 1.08l-5.5 5.25a.75.75 0 11-1.04-1.08l4.158-3.96H3.75A.75.75 0 013 10z"
        clipRule="evenodd"
      />
    </svg>
  );
}

/* ── Section divider ── */

function SectionDivider() {
  return <div className="landing-divider mx-auto max-w-4xl" />;
}

/* ── Section heading with label ── */

function SectionHeading({
  label,
  title,
  description,
}: {
  label?: string;
  title: string;
  description: string;
}) {
  return (
    <div data-reveal className="text-center mb-10 sm:mb-14">
      {label && (
        <span className="inline-block text-[10px] sm:text-[11px] font-semibold tracking-widest uppercase text-gray-400 dark:text-stone-600 mb-2 sm:mb-3">
          {label}
        </span>
      )}
      <h2 className="text-2xl sm:text-3xl md:text-4xl font-bold font-serif tracking-tight text-gray-900 dark:text-stone-50 mb-2.5 sm:mb-3.5">
        {title}
      </h2>
      <p className="text-gray-500 dark:text-stone-400 max-w-md mx-auto text-sm sm:text-[15px] leading-relaxed">
        {description}
      </p>
    </div>
  );
}

/* ── Component ── */

export function LandingPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const containerRef = useScrollReveal();
  const { isAuthenticated, isLoading } = useAuth();

  useEffect(() => {
    if (!isLoading && isAuthenticated) {
      navigate("/chat", { replace: true });
    }
  }, [isLoading, isAuthenticated, navigate]);

  useEffect(() => {
    document.documentElement.classList.add("allow-scroll");
    return () => document.documentElement.classList.remove("allow-scroll");
  }, []);

  const goLogin = useCallback(() => navigate("/auth/login"), [navigate]);

  return (
    <div
      ref={containerRef}
      className="bg-gradient-to-b from-gray-50/80 via-white to-gray-50/60 dark:from-stone-950 dark:via-stone-900 dark:to-stone-950"
    >
      {/* Navbar */}
      <nav className="fixed top-0 inset-x-0 z-50 backdrop-blur-2xl bg-white/70 dark:bg-stone-950/70 border-b border-gray-200/40 dark:border-stone-700/30">
        <div className="max-w-full mx-auto px-4 sm:px-8 py-2.5 sm:py-3 flex items-center justify-between">
          <div
            className="flex items-center gap-2 sm:gap-2.5 cursor-pointer"
            onClick={() => navigate("/")}
          >
            <img
              src="/icons/icon.svg"
              alt=""
              className="w-6 h-6 sm:w-7 sm:h-7 rounded-md"
            />
            <span className="text-base sm:text-lg font-bold font-serif tracking-tight text-gray-900 dark:text-stone-100">
              {APP_NAME}
            </span>
          </div>
          <div className="flex items-center gap-1.5 sm:gap-2">
            <LanguageToggle />
            <ThemeToggle />
          </div>
        </div>
      </nav>

      {/* Hero */}
      <section className="relative pt-24 sm:pt-36 md:pt-48 pb-16 sm:pb-24 overflow-hidden">
        <div
          className="pointer-events-none absolute inset-0 -z-10"
          aria-hidden="true"
        >
          {/* Animated floating gradient orbs */}
          <div className="landing-orb-1 absolute top-10 left-1/4 h-56 sm:h-72 rounded-full bg-amber-200/20 blur-3xl dark:bg-amber-500/5" />
          <div className="landing-orb-2 absolute bottom-0 right-1/4 h-72 sm:h-96 rounded-full bg-rose-200/20 blur-3xl dark:bg-rose-500/5" />
          <div className="landing-orb-3 absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 h-[400px] sm:h-[600px] rounded-full bg-stone-200/25 blur-3xl dark:bg-stone-700/10" />
          <div className="landing-orb-4 absolute bottom-20 left-[10%] h-40 sm:h-56 rounded-full bg-violet-200/15 blur-3xl dark:bg-violet-500/5" />
          {/* Subtle dot grid for texture */}
          <div
            className="absolute inset-0 opacity-[0.03] dark:opacity-[0.05]"
            style={{
              backgroundImage:
                "radial-gradient(circle, currentColor 1px, transparent 1px)",
              backgroundSize: "32px 32px",
            }}
          />
        </div>

        <div className="relative max-w-3xl sm:max-w-4xl mx-auto px-4 sm:px-6 text-center">
          <div
            data-reveal
            className="inline-flex items-center gap-2 rounded-full border border-gray-200/60 dark:border-stone-700/40 bg-white/60 dark:bg-stone-800/40 px-3 py-1 sm:px-4 sm:py-1.5 mb-6 sm:mb-8 text-[11px] sm:text-xs font-medium text-gray-500 dark:text-stone-400 backdrop-blur-sm shadow-sm"
          >
            <span className="relative flex h-2 w-2">
              <span className="absolute inset-0 animate-ping rounded-full bg-emerald-400 opacity-75" />
              <span className="relative inline-flex h-2 w-2 rounded-full bg-emerald-500" />
            </span>
            {t("landing.badge")}
          </div>

          {/* Hero glow behind title */}
          <div className="relative">
            <div className="landing-hero-glow absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-64 sm:w-96 h-32 sm:h-40 bg-gradient-to-r from-violet-200/30 via-amber-200/20 to-rose-200/30 dark:from-violet-500/10 dark:via-amber-500/5 dark:to-rose-500/10 blur-3xl rounded-full pointer-events-none" />
            <h1
              data-reveal
              data-reveal-delay="1"
              className="relative text-5xl sm:text-6xl md:text-8xl font-bold font-serif tracking-tight leading-[1.05] mb-5 sm:mb-7 bg-gradient-to-b from-gray-900 via-gray-600 to-gray-400 dark:from-white dark:via-stone-300 dark:to-stone-500 bg-clip-text text-transparent"
            >
              {APP_NAME}
            </h1>
          </div>

          <p
            data-reveal
            data-reveal-delay="2"
            className="text-sm sm:text-base md:text-lg text-gray-500 dark:text-stone-400 max-w-2xl mx-auto leading-relaxed mb-9 sm:mb-12"
          >
            {t("landing.heroDescription")}
          </p>

          <div
            data-reveal
            data-reveal-delay="3"
            className="flex flex-wrap items-center justify-center gap-3 sm:gap-4"
          >
            <button
              onClick={goLogin}
              className="group inline-flex items-center gap-1.5 sm:gap-2 rounded-xl bg-gray-900 px-6 py-3 sm:px-8 sm:py-3.5 text-sm font-medium text-white shadow-lg shadow-gray-900/20 transition-all duration-300 hover:-translate-y-0.5 hover:bg-gray-800 hover:shadow-xl hover:shadow-gray-900/25 active:translate-y-0 dark:bg-white dark:text-gray-900 dark:shadow-white/10 dark:hover:bg-stone-100 dark:hover:shadow-white/20"
            >
              {t("landing.startUsing")}
              <ArrowIcon />
            </button>
            <a
              href="https://github.com/Yanyutin753/LambChat"
              target="_blank"
              rel="noopener noreferrer"
              className="group inline-flex items-center gap-1.5 sm:gap-2 rounded-xl border border-gray-200/80 dark:border-stone-700/50 bg-white/60 dark:bg-stone-800/40 px-5 py-3 sm:px-6 sm:py-3.5 text-sm font-medium text-gray-700 dark:text-stone-300 transition-all duration-300 hover:-translate-y-0.5 hover:bg-white dark:hover:bg-stone-800/80 hover:shadow-md hover:border-gray-300 dark:hover:border-stone-600 active:translate-y-0 backdrop-blur-sm"
            >
              <GitHubIcon />
              {t("landing.viewOnGitHub")}
            </a>
          </div>

          <div
            data-reveal
            data-reveal-delay="4"
            className="mt-10 sm:mt-14 flex flex-wrap items-center justify-center gap-1.5 sm:gap-2.5"
          >
            {TECH_STACK.map((tech, i) => (
              <span
                key={tech.label}
                data-reveal
                data-reveal-delay={String(i + 1)}
                className={`inline-flex items-center rounded-lg sm:rounded-xl px-2.5 py-1 sm:px-3 sm:py-1.5 text-[11px] sm:text-xs font-medium backdrop-blur-sm shadow-sm ${tech.color}`}
              >
                {tech.label}
              </span>
            ))}
          </div>
        </div>
      </section>

      <SectionDivider />

      {/* Screenshots */}
      <section className="py-12 sm:py-20 md:py-24">
        <div className="max-w-5xl sm:max-w-6xl mx-auto px-4 sm:px-6">
          <SectionHeading
            label={t("landing.sectionLabelInterface")}
            title={t("landing.mainInterface")}
            description={t("landing.mainInterfaceDesc")}
          />
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 sm:gap-5 md:gap-6">
            {MAIN_SHOTS.map((s, i) => (
              <div
                key={s.src}
                data-reveal-scale
                data-reveal-delay={String(i + 1)}
                className="landing-shot group rounded-2xl sm:rounded-3xl border border-gray-200/50 dark:border-stone-700/30 bg-white/70 dark:bg-stone-800/30 overflow-hidden shadow-xl shadow-stone-200/20 dark:shadow-stone-900/20 transition-all duration-500 hover:shadow-2xl hover:shadow-stone-300/30 dark:hover:shadow-stone-800/40 hover:-translate-y-1"
              >
                <div className="relative aspect-[4/3] bg-gray-50 dark:bg-stone-800 overflow-hidden">
                  <img
                    src={s.src}
                    alt={t(`landing.${s.altKey}`)}
                    className="w-full h-full object-cover object-top transition-transform duration-700 group-hover:scale-[1.02]"
                    loading="lazy"
                  />
                </div>
                <div className="px-4 py-3 sm:px-5 sm:py-3.5 flex items-center justify-between">
                  <span className="text-xs sm:text-sm font-medium text-gray-600 dark:text-stone-300">
                    {t(`landing.${s.altKey}`)}
                  </span>
                  <span className="text-[10px] sm:text-[11px] text-gray-400 dark:text-stone-500 font-medium tracking-wide uppercase">
                    {t("landing.preview")}
                  </span>
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Features */}
      <section className="py-12 sm:py-20 md:py-24 relative">
        {/* Subtle background glow */}
        <div
          className="pointer-events-none absolute inset-0 -z-10"
          aria-hidden="true"
        >
          <div className="absolute top-1/3 left-1/2 -translate-x-1/2 w-[600px] h-[400px] bg-gradient-to-b from-violet-100/30 via-transparent to-transparent dark:from-violet-500/5 blur-3xl rounded-full" />
        </div>
        <div className="max-w-5xl sm:max-w-6xl mx-auto px-4 sm:px-6">
          <SectionHeading
            label={t("landing.sectionLabelFeatures")}
            title={t("landing.coreFeatures")}
            description={t("landing.coreFeaturesDesc")}
          />
          <div className="grid sm:grid-cols-3 lg:grid-cols-4 gap-3 sm:gap-4 md:gap-5">
            {FEATURES.map((f, i) => (
              <div
                key={f.titleKey}
                data-reveal
                data-reveal-delay={String(Math.min(i + 1, 6))}
                className="landing-feature-glow group relative rounded-xl sm:rounded-2xl border border-gray-200/50 dark:border-stone-700/30 bg-white/60 dark:bg-stone-800/20 p-4 sm:p-5 md:p-6 transition-all duration-500 hover:bg-white dark:hover:bg-stone-800/60 hover:shadow-xl hover:shadow-stone-200/40 dark:hover:shadow-stone-900/40 hover:-translate-y-1.5"
              >
                <div
                  className={`relative z-10 flex items-center justify-center w-9 h-9 sm:w-11 sm:h-11 rounded-xl bg-gradient-to-br ${f.gradient} text-base sm:text-lg mb-3 sm:mb-4 transition-all duration-300 group-hover:scale-110 group-hover:shadow-lg group-hover:rotate-3`}
                >
                  {f.icon}
                </div>
                <h3 className="relative z-10 text-xs sm:text-sm font-semibold text-gray-800 dark:text-stone-200 mb-1 sm:mb-1.5">
                  {t(`landing.${f.titleKey}`, f.titleKey)}
                </h3>
                <p className="relative z-10 text-[11px] sm:text-xs leading-relaxed text-gray-500 dark:text-stone-400">
                  {t(`landing.${f.descKey}`, f.descKey)}
                </p>
              </div>
            ))}
          </div>
        </div>
      </section>

      <SectionDivider />

      {/* Architecture */}
      <section className="py-12 sm:py-20 md:py-24">
        <div className="max-w-5xl sm:max-w-6xl mx-auto px-4 sm:px-6">
          <SectionHeading
            label={t("landing.sectionLabelArchitecture")}
            title={t("landing.architecture")}
            description={t("landing.architectureDesc")}
          />
          <div
            data-reveal-scale
            className="rounded-2xl sm:rounded-3xl border border-gray-200/50 dark:border-stone-700/30 bg-white/70 dark:bg-stone-800/30 p-3 sm:p-4 md:p-6 shadow-xl shadow-stone-200/20 dark:shadow-stone-900/20"
          >
            <img
              src="/images/best-practice/architecture.png"
              alt={t("landing.architecture")}
              className="w-full rounded-xl sm:rounded-2xl"
              loading="lazy"
            />
          </div>
          <div className="mt-8 sm:mt-10 grid grid-cols-3 sm:grid-cols-6 gap-2 sm:gap-3 md:gap-4">
            {STATS.map((s, i) => (
              <div
                key={s.key}
                data-reveal
                data-reveal-delay={String(i + 1)}
                className="landing-stat-glow rounded-xl sm:rounded-2xl border border-gray-200/50 dark:border-stone-700/30 bg-white/50 dark:bg-stone-800/20 p-3 sm:p-4 md:p-5 text-center transition-all duration-300 hover:bg-white dark:hover:bg-stone-800/40 hover:shadow-lg hover:-translate-y-0.5"
              >
                <div className="text-xl sm:text-2xl md:text-3xl font-bold font-serif text-gray-800 dark:text-stone-100 leading-none mb-1 sm:mb-1.5">
                  <AnimatedNumber value={s.num} />
                </div>
                <div className="text-[10px] sm:text-xs text-gray-500 dark:text-stone-400 leading-snug">
                  {t(`landing.${s.key}`, s.key)}
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      <SectionDivider />

      {/* Management Panels */}
      <section className="py-12 sm:py-20 md:py-24">
        <div className="max-w-5xl sm:max-w-6xl mx-auto px-4 sm:px-6">
          <SectionHeading
            label={t("landing.sectionLabelDashboard")}
            title={t("landing.managementPanels")}
            description={t("landing.managementPanelsDesc")}
          />
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4 sm:gap-5 md:gap-6">
            {MGMT_SHOTS.map((s, i) => (
              <div
                key={s.src}
                data-reveal-scale
                data-reveal-delay={String(i + 1)}
                className="landing-shot group rounded-2xl sm:rounded-3xl border border-gray-200/50 dark:border-stone-700/30 bg-white/70 dark:bg-stone-800/30 overflow-hidden shadow-xl shadow-stone-200/20 dark:shadow-stone-900/20 transition-all duration-500 hover:shadow-2xl hover:shadow-stone-300/30 dark:hover:shadow-stone-800/40 hover:-translate-y-1"
              >
                <div className="relative aspect-[4/3] bg-gray-50 dark:bg-stone-800 overflow-hidden">
                  <img
                    src={s.src}
                    alt={t(`landing.${s.altKey}`)}
                    className="w-full h-full object-cover object-top transition-transform duration-700 group-hover:scale-[1.02]"
                    loading="lazy"
                  />
                </div>
                <div className="px-4 py-3 sm:px-5 sm:py-3.5 flex items-center justify-between">
                  <span className="text-xs sm:text-sm font-medium text-gray-600 dark:text-stone-300">
                    {t(`landing.${s.altKey}`)}
                  </span>
                  <span className="text-[10px] sm:text-[11px] text-gray-400 dark:text-stone-500 font-medium tracking-wide uppercase">
                    {t(`landing.${s.altKey}`)}
                  </span>
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      <SectionDivider />

      {/* Responsive Design */}
      <section className="py-12 sm:py-20 md:py-24 relative">
        <div
          className="pointer-events-none absolute inset-0 -z-10"
          aria-hidden="true"
        >
          <div className="absolute bottom-0 left-1/2 -translate-x-1/2 w-[500px] h-[300px] bg-gradient-to-t from-amber-100/30 via-transparent to-transparent dark:from-amber-500/5 blur-3xl rounded-full" />
        </div>
        <div className="max-w-5xl sm:max-w-6xl mx-auto px-4 sm:px-6">
          <SectionHeading
            label={t("landing.sectionLabelResponsive")}
            title={t("landing.responsiveDesign")}
            description={t("landing.responsiveDesignDesc")}
          />
          <div className="flex flex-col sm:flex-row items-center justify-center gap-5 sm:gap-8">
            {RESPONSIVE_SHOTS.map((s, i) => (
              <div
                key={s.src}
                data-reveal-scale
                data-reveal-delay={String(i + 1)}
                className="landing-shot rounded-2xl sm:rounded-3xl border border-gray-200/50 dark:border-stone-700/30 bg-white/70 dark:bg-stone-800/30 p-2 sm:p-3 shadow-xl shadow-stone-200/20 dark:shadow-stone-900/20 overflow-hidden transition-all duration-500 hover:shadow-2xl hover:-translate-y-1"
              >
                <img
                  src={s.src}
                  alt={t(`landing.${s.altKey}`)}
                  className="w-auto max-h-52 sm:max-h-72 md:max-h-80 rounded-xl sm:rounded-2xl object-contain"
                  loading="lazy"
                />
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* CTA */}
      <section className="py-14 sm:py-24">
        <div className="max-w-3xl mx-auto px-4 sm:px-6">
          <div
            data-reveal
            className="relative rounded-2xl sm:rounded-3xl p-[1px] bg-gradient-to-b from-gray-300/80 via-gray-200/40 to-gray-300/80 dark:from-stone-600/50 dark:via-stone-700/20 dark:to-stone-600/50 overflow-hidden shadow-2xl shadow-stone-200/30 dark:shadow-stone-900/30"
          >
            <div className="absolute inset-0 bg-gradient-to-r from-transparent via-white/30 dark:via-white/10 to-transparent -translate-x-full animate-cta-shimmer" />
            <div className="relative rounded-2xl sm:rounded-3xl bg-gradient-to-b from-gray-50/90 to-white dark:from-stone-950/90 dark:to-stone-900/90 px-6 py-14 sm:px-12 sm:py-20 text-center">
              <h2 className="text-2xl sm:text-3xl md:text-4xl font-bold font-serif tracking-tight text-gray-900 dark:text-stone-50 mb-3 sm:mb-4">
                {t("landing.ctaTitle")}
              </h2>
              <p className="text-gray-500 dark:text-stone-400 mb-8 sm:mb-10 text-sm sm:text-base max-w-md mx-auto leading-relaxed">
                {t("landing.ctaDescription")}
              </p>
              <div className="flex flex-wrap items-center justify-center gap-3 sm:gap-4">
                <button
                  onClick={goLogin}
                  className="group inline-flex items-center gap-1.5 sm:gap-2 rounded-xl bg-gray-900 px-6 py-3 sm:px-8 sm:py-3.5 text-sm font-medium text-white shadow-lg shadow-gray-900/20 transition-all duration-300 hover:-translate-y-0.5 hover:bg-gray-800 hover:shadow-xl hover:shadow-gray-900/25 active:translate-y-0 dark:bg-white dark:text-gray-900 dark:shadow-white/10 dark:hover:bg-stone-100 dark:hover:shadow-white/20"
                >
                  {t("landing.getStarted")}
                  <ArrowIcon />
                </button>
                <a
                  href="https://github.com/Yanyutin753/LambChat"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="group inline-flex items-center gap-1.5 sm:gap-2 rounded-xl border border-gray-200/80 dark:border-stone-700/50 bg-white/60 dark:bg-stone-800/40 px-5 py-3 sm:px-6 sm:py-3.5 text-sm font-medium text-gray-700 dark:text-stone-300 transition-all duration-300 hover:-translate-y-0.5 hover:bg-white dark:hover:bg-stone-800/80 hover:shadow-md hover:border-gray-300 dark:hover:border-stone-600 active:translate-y-0"
                >
                  <GitHubIcon />
                  {t("landing.viewOnGitHub")}
                </a>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Footer */}
      <footer className="border-t border-gray-200/30 dark:border-stone-700/20 py-6 sm:py-8">
        <div className="max-w-full mx-auto px-4 sm:px-6 flex flex-col sm:flex-row items-center justify-between gap-3 sm:gap-4 text-[11px] sm:text-xs text-gray-400 dark:text-stone-500">
          <div className="flex items-center gap-1.5">
            <img src="/icons/icon.svg" alt="" className="h-3.5 w-3.5 rounded" />
            <span>
              {t("landing.poweredBy")}{" "}
              <a
                href="https://github.com/Yanyutin753/LambChat"
                target="_blank"
                rel="noopener noreferrer"
                className="font-serif text-gray-500 hover:text-gray-700 dark:text-stone-400 dark:hover:text-stone-200 transition-colors"
              >
                {APP_NAME}
              </a>
            </span>
          </div>
          <div className="flex items-center gap-2 sm:gap-3">
            <a
              href="https://github.com/Yanyutin753/LambChat"
              target="_blank"
              rel="noopener noreferrer"
              className="hover:text-gray-600 dark:hover:text-stone-300 transition-colors"
            >
              GitHub
            </a>
            <span className="text-gray-300 dark:text-stone-600">&middot;</span>
            <span>MIT</span>
            <span className="text-gray-300 dark:text-stone-600">&middot;</span>
            <span>{new Date().getFullYear()}</span>
          </div>
        </div>
      </footer>
    </div>
  );
}

export default LandingPage;
