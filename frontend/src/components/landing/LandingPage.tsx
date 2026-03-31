import { useEffect, useRef, useState, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { ThemeToggle } from "../common/ThemeToggle";
import { LanguageToggle } from "../common/LanguageToggle";
import { ImageViewer } from "../common/ImageViewer";
import { useAuth } from "../../hooks/useAuth";
import { APP_NAME, GITHUB_URL } from "../../constants";
import {
  FEATURES,
  TECH_STACK,
  MAIN_SHOTS,
  MGMT_SHOTS,
  RESPONSIVE_SHOTS,
  STATS,
} from "./data";

/* ─────────────────── Hooks ─────────────────── */

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

function useScrollProgress() {
  const [progress, setProgress] = useState(0);
  useEffect(() => {
    const h = () => {
      const top = window.scrollY;
      const docH = document.documentElement.scrollHeight - window.innerHeight;
      setProgress(docH > 0 ? (top / docH) * 100 : 0);
    };
    window.addEventListener("scroll", h, { passive: true });
    return () => window.removeEventListener("scroll", h);
  }, []);
  return progress;
}

function useActiveSection(ids: string[]) {
  const [active, setActive] = useState("");
  useEffect(() => {
    const h = () => {
      for (let i = ids.length - 1; i >= 0; i--) {
        const el = document.getElementById(ids[i]);
        if (el && el.getBoundingClientRect().top <= 120) {
          setActive(ids[i]);
          return;
        }
      }
      setActive(ids[0]);
    };
    window.addEventListener("scroll", h, { passive: true });
    h();
    return () => window.removeEventListener("scroll", h);
  }, [ids]);
  return active;
}

/* ─────────────────── Small components ─────────────────── */

function AnimatedNumber({ value }: { value: string }) {
  const [display, setDisplay] = useState(value);
  const ref = useRef<HTMLSpanElement>(null);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const m = value.match(/^(\d+)/);
    if (!m) return;
    const num = parseInt(m[1]);
    const suf = value.slice(m[1].length);
    let start = 0;
    const obs = new IntersectionObserver(
      ([e]) => {
        if (e.isIntersecting) {
          const step = (ts: number) => {
            if (!start) start = ts;
            const p = Math.min((ts - start) / 1400, 1);
            setDisplay(
              Math.round((1 - Math.pow(1 - p, 4)) * num).toString() + suf,
            );
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

function ArrowUpIcon() {
  return (
    <svg className="w-4 h-4" viewBox="0 0 20 20" fill="currentColor">
      <path
        fillRule="evenodd"
        d="M10 17a.75.75 0 01-.75-.75V5.612L5.29 9.77a.75.75 0 01-1.08-1.04l5.25-5.5a.75.75 0 011.08 0l5.25 5.5a.75.75 0 11-1.08 1.04l-3.96-4.158V16.25A.75.75 0 0110 17z"
        clipRule="evenodd"
      />
    </svg>
  );
}

function ZoomIcon() {
  return (
    <svg className="w-4 h-4" viewBox="0 0 20 20" fill="currentColor">
      <path d="M10 12.5a2.5 2.5 0 100-5 2.5 2.5 0 000 5z" />
      <path
        fillRule="evenodd"
        d="M.664 10.59a1.651 1.651 0 010-1.186A10.004 10.004 0 0110 3c4.257 0 7.893 2.66 9.336 6.41.147.381.146.804 0 1.186A10.004 10.004 0 0110 17c-4.257 0-7.893-2.66-9.336-6.41zM14 10a4 4 0 11-8 0 4 4 0 018 0z"
        clipRule="evenodd"
      />
    </svg>
  );
}

function MenuIcon() {
  return (
    <svg className="w-5 h-5" viewBox="0 0 20 20" fill="currentColor">
      <path
        fillRule="evenodd"
        d="M2 4.75A.75.75 0 012.75 4h14.5a.75.75 0 010 1.5H2.75A.75.75 0 012 4.75zm0 10.5a.75.75 0 01.75-.75h14.5a.75.75 0 010 1.5H2.75a.75.75 0 01-.75-.75zM2 10a.75.75 0 01.75-.75h14.5a.75.75 0 010 1.5H2.75A.75.75 0 012 10z"
        clipRule="evenodd"
      />
    </svg>
  );
}

function CloseIcon() {
  return (
    <svg className="w-5 h-5" viewBox="0 0 20 20" fill="currentColor">
      <path d="M6.28 5.22a.75.75 0 00-1.06 1.06L8.94 10l-3.72 3.72a.75.75 0 101.06 1.06L10 11.06l3.72 3.72a.75.75 0 101.06-1.06L11.06 10l3.72-3.72a.75.75 0 00-1.06-1.06L10 8.94 6.28 5.22z" />
    </svg>
  );
}

function SectionDivider() {
  return <div className="landing-divider mx-auto max-w-5xl" />;
}

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
    <div data-reveal className="text-center mb-10 sm:mb-14 lg:mb-16 px-2">
      {label && (
        <div className="inline-flex items-center gap-2 mb-4 sm:mb-5">
          <span className="w-1.5 h-1.5 rounded-full bg-violet-500 dark:bg-violet-400" />
          <span className="text-[11px] sm:text-xs font-semibold tracking-[0.08em] uppercase text-stone-400 dark:text-stone-500">
            {label}
          </span>
        </div>
      )}
      <h2 className="text-2xl sm:text-3xl lg:text-[2.25rem] font-bold font-serif tracking-[-0.025em] text-stone-900 dark:text-stone-50 mb-3">
        {title}
      </h2>
      <p className="text-stone-500 dark:text-stone-400 max-w-lg mx-auto text-sm sm:text-[15px] leading-relaxed">
        {description}
      </p>
    </div>
  );
}

/* Screenshot card with zoom hint */
function ScreenshotCard({
  src,
  alt,
  onClick,
  label,
}: {
  src: string;
  alt: string;
  onClick: () => void;
  label?: string;
}) {
  return (
    <div
      data-reveal-scale
      className="group rounded-2xl border border-stone-200/60 dark:border-stone-800/60 bg-white dark:bg-stone-900/80 overflow-hidden shadow-sm hover:shadow-lg hover:shadow-stone-200/40 dark:hover:shadow-stone-900/50 transition-all duration-400 hover:-translate-y-0.5 cursor-pointer"
      onClick={onClick}
    >
      <div className="relative aspect-[4/3] bg-stone-50 dark:bg-stone-800/40 overflow-hidden">
        <img
          src={src}
          alt={alt}
          className="w-full h-full object-cover object-top transition-transform duration-500 group-hover:scale-[1.02]"
          loading="lazy"
        />
        <div className="absolute inset-0 bg-black/0 group-hover:bg-black/5 dark:group-hover:bg-black/20 transition-colors duration-300 flex items-center justify-center">
          <div className="opacity-0 group-hover:opacity-100 transition-all duration-300 scale-75 group-hover:scale-100 w-8 h-8 rounded-lg bg-white/95 dark:bg-stone-800/95 shadow-md flex items-center justify-center text-stone-500 dark:text-stone-400">
            <ZoomIcon />
          </div>
        </div>
      </div>
      <div className="px-4 py-3 flex items-center justify-between border-t border-stone-100 dark:border-stone-800/60">
        <span className="text-xs font-medium text-stone-600 dark:text-stone-300 truncate">
          {alt}
        </span>
        {label && (
          <span className="text-[10px] text-stone-400 dark:text-stone-500 font-medium tracking-wider uppercase shrink-0 ml-2">
            {label}
          </span>
        )}
      </div>
    </div>
  );
}

/* ─────────────────── Constants ─────────────────── */

const SECTION_IDS = [
  "interface",
  "features",
  "architecture",
  "dashboard",
  "responsive",
];

const NAV_ITEMS = [
  { id: "interface", labelKey: "mainInterface" },
  { id: "features", labelKey: "coreFeatures" },
  { id: "architecture", labelKey: "architecture" },
  { id: "dashboard", labelKey: "managementPanels" },
];

/* ─────────────────── Page ─────────────────── */

export function LandingPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const containerRef = useScrollReveal();
  const { isAuthenticated, isLoading } = useAuth();
  const scrollProgress = useScrollProgress();
  const activeSection = useActiveSection(SECTION_IDS);
  const [showBackTop, setShowBackTop] = useState(false);
  const [showNav, setShowNav] = useState(false);
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const [viewerSrc, setViewerSrc] = useState<string | null>(null);
  const [viewerAlt, setViewerAlt] = useState("");

  const openViewer = useCallback((src: string, alt: string) => {
    setViewerSrc(src);
    setViewerAlt(alt);
    setMobileMenuOpen(false);
  }, []);
  const closeViewer = useCallback(() => setViewerSrc(null), []);

  useEffect(() => {
    if (!isLoading && isAuthenticated) navigate("/chat", { replace: true });
  }, [isLoading, isAuthenticated, navigate]);

  useEffect(() => {
    document.documentElement.classList.add("allow-scroll");
    return () => document.documentElement.classList.remove("allow-scroll");
  }, []);

  useEffect(() => {
    const h = () => {
      setShowBackTop(window.scrollY > 600);
      setShowNav(window.scrollY > 300);
    };
    window.addEventListener("scroll", h, { passive: true });
    return () => window.removeEventListener("scroll", h);
  }, []);

  useEffect(() => {
    const mq = window.matchMedia("(min-width: 768px)");
    const h = (e: MediaQueryListEvent) => {
      if (e.matches) setMobileMenuOpen(false);
    };
    mq.addEventListener("change", h);
    return () => mq.removeEventListener("change", h);
  }, []);

  useEffect(() => {
    if (mobileMenuOpen) {
      document.body.style.overflow = "hidden";
    } else {
      document.body.style.overflow = "";
    }
    return () => {
      document.body.style.overflow = "";
    };
  }, [mobileMenuOpen]);

  const goLogin = useCallback(() => {
    setMobileMenuOpen(false);
    navigate("/auth/login");
  }, [navigate]);

  const scrollToSection = useCallback((id: string) => {
    setMobileMenuOpen(false);
    document.getElementById(id)?.scrollIntoView({ behavior: "smooth" });
  }, []);

  const scrollToTop = useCallback(
    () => window.scrollTo({ top: 0, behavior: "smooth" }),
    [],
  );

  return (
    <div ref={containerRef} className="bg-white dark:bg-stone-950 antialiased">
      {/* ── Progress bar ── */}
      <div
        className="landing-progress-bar"
        style={{ width: `${scrollProgress}%` }}
      />

      {/* ── Navigation ── */}
      <nav className="fixed top-0 inset-x-0 z-50 bg-white/95 dark:bg-stone-950/95 border-b border-stone-100 dark:border-stone-800/80">
        <div className="max-w-6xl mx-auto px-5 sm:px-8 h-14 flex items-center justify-between">
          <div
            className="flex items-center gap-2.5 cursor-pointer"
            onClick={() => navigate("/")}
          >
            <img
              src="/icons/icon.svg"
              alt=""
              className="w-6 h-6 sm:w-7 sm:h-7 rounded-lg"
            />
            <span className="text-sm sm:text-[15px] font-bold tracking-tight text-stone-900 dark:text-stone-100 font-serif">
              {APP_NAME}
            </span>
          </div>

          {/* Desktop nav links */}
          <div
            className={`hidden md:flex items-center gap-0.5 absolute left-1/2 -translate-x-1/2 transition-all duration-300 ${
              showNav
                ? "opacity-100 translate-y-0"
                : "opacity-0 -translate-y-1 pointer-events-none"
            }`}
          >
            {NAV_ITEMS.map((item) => (
              <button
                key={item.id}
                onClick={() => scrollToSection(item.id)}
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
              className="md:hidden ml-0.5 p-2 rounded-lg text-stone-500 hover:text-stone-700 dark:text-stone-400 dark:hover:text-stone-200 hover:bg-stone-100 dark:hover:bg-stone-800 transition-colors"
              onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
              aria-label="Toggle menu"
            >
              {mobileMenuOpen ? <CloseIcon /> : <MenuIcon />}
            </button>
          </div>
        </div>
      </nav>

      {/* ── Mobile menu overlay ── */}
      {mobileMenuOpen && (
        <div className="fixed inset-0 z-40 md:hidden">
          <div
            className="absolute inset-0 bg-black/20 dark:bg-black/40"
            onClick={() => setMobileMenuOpen(false)}
          />
          <div className="landing-mobile-menu absolute top-14 inset-x-0 bg-white dark:bg-stone-900 border-b border-stone-100 dark:border-stone-800/80 shadow-xl shadow-stone-200/30 dark:shadow-stone-900/50">
            <div className="max-w-6xl mx-auto px-4 py-3">
              {NAV_ITEMS.map((item) => (
                <button
                  key={item.id}
                  onClick={() => scrollToSection(item.id)}
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
      )}

      {/* ── Hero ── */}
      <section className="relative pt-28 sm:pt-40 md:pt-52 pb-20 sm:pb-32 lg:pb-40 overflow-hidden">
        {/* Subtle grid background */}
        <div
          className="pointer-events-none absolute inset-0 -z-10"
          aria-hidden="true"
        >
          <div className="absolute inset-0 bg-[linear-gradient(to_right,rgba(0,0,0,0.03)_1px,transparent_1px),linear-gradient(to_bottom,rgba(0,0,0,0.03)_1px,transparent_1px)] dark:bg-[linear-gradient(to_right,rgba(255,255,255,0.03)_1px,transparent_1px),linear-gradient(to_bottom,rgba(255,255,255,0.03)_1px,transparent_1px)] bg-[size:48px_48px]" />
          <div className="landing-orb-1 absolute top-20 left-[15%] h-48 sm:h-80 rounded-full bg-amber-200/25 dark:bg-amber-500/8" />
          <div className="landing-orb-2 absolute bottom-0 right-[15%] h-48 sm:h-96 rounded-full bg-rose-200/25 dark:bg-rose-500/8" />
          <div className="landing-orb-3 absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 h-[300px] sm:h-[700px] rounded-full bg-stone-200/25 dark:bg-stone-700/15" />
        </div>

        <div className="relative max-w-3xl sm:max-w-4xl mx-auto px-5 sm:px-6 text-center">
          {/* Badge */}
          <div
            data-reveal
            className="inline-flex items-center gap-2.5 rounded-full border border-stone-200/80 dark:border-stone-700/50 bg-white dark:bg-stone-800/60 px-4 py-2 mb-8 sm:mb-10 text-xs font-medium text-stone-500 dark:text-stone-400 shadow-sm"
          >
            <span className="relative flex h-2 w-2">
              <span className="absolute inset-0 animate-ping rounded-full bg-emerald-400 opacity-75" />
              <span className="relative inline-flex h-2 w-2 rounded-full bg-emerald-500" />
            </span>
            {t("landing.badge")}
          </div>

          {/* Title */}
          <h1
            data-reveal
            data-reveal-delay="1"
            className="text-5xl sm:text-[4.5rem] md:text-7xl lg:text-8xl font-extrabold font-serif tracking-[-0.04em] leading-[1.05] sm:leading-[1.0] mb-6 sm:mb-8 text-stone-900 dark:text-white"
          >
            {APP_NAME}
          </h1>

          {/* Description */}
          <p
            data-reveal
            data-reveal-delay="2"
            className="text-base sm:text-lg lg:text-xl text-stone-500 dark:text-stone-400 max-w-xl mx-auto leading-[1.7] mb-10 sm:mb-12 px-1"
          >
            {t("landing.heroDescription")}
          </p>

          {/* CTAs */}
          <div
            data-reveal
            data-reveal-delay="3"
            className="flex flex-col sm:flex-row items-center justify-center gap-3 sm:gap-4 max-w-xs sm:max-w-none mx-auto"
          >
            <button
              onClick={goLogin}
              className="w-full sm:w-auto group inline-flex items-center justify-center gap-2 rounded-xl bg-stone-900 dark:bg-white px-7 py-3.5 sm:px-8 sm:py-3.5 text-sm font-semibold text-white dark:text-stone-900 shadow-lg shadow-stone-900/15 dark:shadow-white/10 transition-all duration-200 hover:-translate-y-0.5 hover:bg-stone-800 dark:hover:bg-stone-100 hover:shadow-xl active:translate-y-0"
            >
              {t("landing.startUsing")}
              <ArrowIcon />
            </button>
            <a
              href={GITHUB_URL}
              target="_blank"
              rel="noopener noreferrer"
              className="w-full sm:w-auto group inline-flex items-center justify-center gap-2 rounded-xl border border-stone-200 dark:border-stone-700/50 bg-white dark:bg-stone-800/40 px-7 py-3.5 sm:px-8 sm:py-3.5 text-sm font-medium text-stone-600 dark:text-stone-300 transition-all duration-200 hover:-translate-y-0.5 hover:bg-stone-50 dark:hover:bg-stone-800/70 hover:shadow-md hover:border-stone-300 dark:hover:border-stone-600 active:translate-y-0"
            >
              <GitHubIcon />
              {t("landing.viewOnGitHub")}
            </a>
          </div>

          {/* Tech stack */}
          <div
            data-reveal
            data-reveal-delay="4"
            className="mt-10 sm:mt-14 flex flex-wrap items-center justify-center gap-2 sm:gap-3"
          >
            {TECH_STACK.map((tech, i) => (
              <span
                key={tech.labelKey}
                data-reveal
                data-reveal-delay={String(i + 1)}
                className={`inline-flex items-center rounded-lg px-3 py-1.5 text-[11px] sm:text-xs font-medium ${tech.color}`}
              >
                {t(`landing.${tech.labelKey}`)}
              </span>
            ))}
          </div>
        </div>
      </section>

      <SectionDivider />

      {/* ── Main Interface ── */}
      <section id="interface" className="py-14 sm:py-20 lg:py-28 scroll-mt-14">
        <div className="max-w-5xl lg:max-w-6xl mx-auto px-5 sm:px-6">
          <SectionHeading
            label={t("landing.sectionLabelInterface")}
            title={t("landing.mainInterface")}
            description={t("landing.mainInterfaceDesc")}
          />
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 sm:gap-5">
            {MAIN_SHOTS.map((s) => (
              <ScreenshotCard
                key={s.src}
                src={s.src}
                alt={t(`landing.${s.altKey}`)}
                onClick={() => openViewer(s.src, t(`landing.${s.altKey}`))}
                label={t("landing.preview")}
              />
            ))}
          </div>
        </div>
      </section>

      {/* ── Core Features (bento grid) ── */}
      <section
        id="features"
        className="py-14 sm:py-20 lg:py-28 relative scroll-mt-14 bg-stone-50/60 dark:bg-stone-900/20"
      >
        <div className="max-w-5xl lg:max-w-6xl mx-auto px-5 sm:px-6">
          <SectionHeading
            label={t("landing.sectionLabelFeatures")}
            title={t("landing.coreFeatures")}
            description={t("landing.coreFeaturesDesc")}
          />
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3 sm:gap-4">
            {/* First two features — span 2 cols on lg */}
            {FEATURES.slice(0, 2).map((f, i) => (
              <div
                key={f.titleKey}
                data-reveal
                data-reveal-delay={String(i + 1)}
                className="sm:col-span-1 lg:col-span-2 landing-feature-glow group relative rounded-2xl border border-stone-200/60 dark:border-stone-800/60 bg-white dark:bg-stone-900/80 p-6 sm:p-8 transition-all duration-300 hover:shadow-lg hover:shadow-stone-200/40 dark:hover:shadow-stone-900/50 hover:-translate-y-0.5"
              >
                <div
                  className={`flex items-center justify-center w-10 h-10 sm:w-11 sm:h-11 rounded-xl bg-gradient-to-br ${f.gradient} text-lg sm:text-xl mb-4 sm:mb-5 transition-transform duration-200 group-hover:scale-110`}
                >
                  {f.icon}
                </div>
                <h3 className="text-sm sm:text-[15px] font-semibold text-stone-900 dark:text-stone-100 mb-1.5">
                  {t(`landing.${f.titleKey}`, f.titleKey)}
                </h3>
                <p className="text-xs sm:text-[13px] leading-relaxed text-stone-500 dark:text-stone-400">
                  {t(`landing.${f.descKey}`, f.descKey)}
                </p>
              </div>
            ))}
            {/* Remaining features */}
            {FEATURES.slice(2).map((f, i) => (
              <div
                key={f.titleKey}
                data-reveal
                data-reveal-delay={String(Math.min(i + 1, 6))}
                className="landing-feature-glow group relative rounded-2xl border border-stone-200/60 dark:border-stone-800/60 bg-white dark:bg-stone-900/80 p-5 sm:p-6 transition-all duration-300 hover:shadow-lg hover:shadow-stone-200/40 dark:hover:shadow-stone-900/50 hover:-translate-y-0.5"
              >
                <div
                  className={`flex items-center justify-center w-9 h-9 sm:w-10 sm:h-10 rounded-xl bg-gradient-to-br ${f.gradient} text-base sm:text-lg mb-3 sm:mb-4 transition-transform duration-200 group-hover:scale-110`}
                >
                  {f.icon}
                </div>
                <h3 className="text-xs sm:text-[13px] font-semibold text-stone-900 dark:text-stone-100 mb-1 sm:mb-1.5">
                  {t(`landing.${f.titleKey}`, f.titleKey)}
                </h3>
                <p className="text-[11px] sm:text-xs leading-relaxed text-stone-500 dark:text-stone-400">
                  {t(`landing.${f.descKey}`, f.descKey)}
                </p>
              </div>
            ))}
          </div>
        </div>
      </section>

      <SectionDivider />

      {/* ── Architecture ── */}
      <section
        id="architecture"
        className="py-14 sm:py-20 lg:py-28 scroll-mt-14"
      >
        <div className="max-w-5xl lg:max-w-6xl mx-auto px-5 sm:px-6">
          <SectionHeading
            label={t("landing.sectionLabelArchitecture")}
            title={t("landing.architecture")}
            description={t("landing.architectureDesc")}
          />
          <div
            data-reveal-scale
            className="rounded-2xl border border-stone-200/60 dark:border-stone-800/60 bg-white dark:bg-stone-900/80 p-2 sm:p-3 md:p-5 shadow-sm cursor-pointer hover:shadow-lg hover:shadow-stone-200/40 dark:hover:shadow-stone-900/50 transition-shadow duration-400"
            onClick={() =>
              openViewer(
                "/images/best-practice/architecture.png",
                t("landing.architecture"),
              )
            }
          >
            <img
              src="/images/best-practice/architecture.png"
              alt={t("landing.architecture")}
              className="w-full rounded-xl"
              loading="lazy"
            />
          </div>

          {/* Stats strip */}
          <div className="mt-8 sm:mt-12 grid grid-cols-2 sm:grid-cols-5 gap-3 sm:gap-4">
            {STATS.map((s, i) => (
              <div
                key={s.key}
                data-reveal
                data-reveal-delay={String(i + 1)}
                className={`landing-stat-glow rounded-xl border border-stone-200/60 dark:border-stone-800/60 bg-stone-50/60 dark:bg-stone-800/20 p-4 sm:p-5 text-center transition-all duration-300 hover:bg-white dark:hover:bg-stone-800/40 hover:shadow-md hover:-translate-y-0.5 ${
                  STATS.length % 2 !== 0 && i === STATS.length - 1
                    ? "col-span-2 sm:col-span-1"
                    : ""
                }`}
              >
                <div className="text-xl sm:text-2xl lg:text-3xl font-bold font-serif tracking-tight text-stone-900 dark:text-stone-100 leading-none mb-1.5 sm:mb-2">
                  <AnimatedNumber value={s.num} />
                </div>
                <div className="text-[10px] sm:text-xs text-stone-500 dark:text-stone-400 leading-snug">
                  {t(`landing.${s.key}`, s.key)}
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      <SectionDivider />

      {/* ── Management Panels ── */}
      <section
        id="dashboard"
        className="py-14 sm:py-20 lg:py-28 scroll-mt-14 bg-stone-50/60 dark:bg-stone-900/20"
      >
        <div className="max-w-5xl lg:max-w-6xl mx-auto px-5 sm:px-6">
          <SectionHeading
            label={t("landing.sectionLabelDashboard")}
            title={t("landing.managementPanels")}
            description={t("landing.managementPanelsDesc")}
          />
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4 sm:gap-5">
            {MGMT_SHOTS.map((s) => (
              <ScreenshotCard
                key={s.src}
                src={s.src}
                alt={t(`landing.${s.altKey}`)}
                onClick={() => openViewer(s.src, t(`landing.${s.altKey}`))}
              />
            ))}
          </div>
        </div>
      </section>

      <SectionDivider />

      {/* ── Responsive Design ── */}
      <section id="responsive" className="py-14 sm:py-20 lg:py-28 scroll-mt-14">
        <div className="max-w-5xl lg:max-w-6xl mx-auto px-5 sm:px-6">
          <SectionHeading
            label={t("landing.sectionLabelResponsive")}
            title={t("landing.responsiveDesign")}
            description={t("landing.responsiveDesignDesc")}
          />
          <div className="flex flex-col sm:flex-row items-center justify-center gap-4 sm:gap-10">
            {RESPONSIVE_SHOTS.map((s) => (
              <div
                key={s.src}
                data-reveal-scale
                className="group rounded-2xl border border-stone-200/60 dark:border-stone-800/60 bg-white dark:bg-stone-900/80 p-2 sm:p-3.5 shadow-sm hover:shadow-lg hover:shadow-stone-200/40 dark:hover:shadow-stone-900/50 overflow-hidden transition-all duration-300 hover:-translate-y-0.5 cursor-pointer"
                onClick={() => openViewer(s.src, t(`landing.${s.altKey}`))}
              >
                <div className="relative">
                  <img
                    src={s.src}
                    alt={t(`landing.${s.altKey}`)}
                    className="w-auto max-h-44 sm:max-h-72 lg:max-h-80 rounded-xl object-contain"
                    loading="lazy"
                  />
                  <div className="absolute inset-0 bg-black/0 group-hover:bg-black/5 dark:group-hover:bg-black/20 transition-colors duration-300 flex items-center justify-center rounded-xl">
                    <div className="opacity-0 group-hover:opacity-100 transition-all duration-300 scale-75 group-hover:scale-100 w-8 h-8 rounded-lg bg-white/95 dark:bg-stone-800/95 shadow-md flex items-center justify-center text-stone-500 dark:text-stone-400">
                      <ZoomIcon />
                    </div>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ── CTA ── */}
      <section className="py-14 sm:py-20 lg:py-28">
        <div className="max-w-3xl mx-auto px-5 sm:px-6">
          <div
            data-reveal
            className="relative rounded-2xl p-[1px] overflow-hidden"
            style={{
              background:
                "linear-gradient(135deg, #e7e5e4 0%, #c4b5fd 50%, #e7e5e4 100%)",
            }}
          >
            <div className="absolute inset-0 bg-gradient-to-r from-transparent via-white/40 dark:via-white/10 to-transparent -translate-x-full animate-cta-shimmer" />
            <div className="relative rounded-2xl bg-white dark:bg-stone-900 px-6 py-14 sm:px-14 sm:py-24 text-center">
              <h2 className="text-xl sm:text-3xl lg:text-[2.25rem] font-bold font-serif tracking-[-0.025em] text-stone-900 dark:text-stone-50 mb-3 sm:mb-4">
                {t("landing.ctaTitle")}
              </h2>
              <p className="text-stone-500 dark:text-stone-400 mb-8 sm:mb-10 text-sm sm:text-base max-w-md mx-auto leading-relaxed px-2">
                {t("landing.ctaDescription")}
              </p>
              <div className="flex flex-col sm:flex-row items-center justify-center gap-3 sm:gap-4 max-w-xs sm:max-w-none mx-auto">
                <button
                  onClick={goLogin}
                  className="w-full sm:w-auto group inline-flex items-center justify-center gap-2 rounded-xl bg-stone-900 dark:bg-white px-7 py-3.5 sm:px-8 sm:py-3.5 text-sm font-semibold text-white dark:text-stone-900 shadow-lg shadow-stone-900/15 dark:shadow-white/10 transition-all duration-200 hover:-translate-y-0.5 hover:bg-stone-800 dark:hover:bg-stone-100 active:translate-y-0"
                >
                  {t("landing.getStarted")}
                  <ArrowIcon />
                </button>
                <a
                  href={GITHUB_URL}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="w-full sm:w-auto group inline-flex items-center justify-center gap-2 rounded-xl border border-stone-200 dark:border-stone-700/50 bg-white dark:bg-stone-800/40 px-7 py-3.5 sm:px-8 sm:py-3.5 text-sm font-medium text-stone-600 dark:text-stone-300 transition-all duration-200 hover:-translate-y-0.5 hover:bg-stone-50 dark:hover:bg-stone-800/70 hover:shadow-md hover:border-stone-300 dark:hover:border-stone-600 active:translate-y-0"
                >
                  <GitHubIcon />
                  {t("landing.viewOnGitHub")}
                </a>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* ── Footer ── */}
      <footer className="border-t border-stone-100 dark:border-stone-800/80 bg-stone-50/50 dark:bg-stone-900/30">
        <div className="max-w-6xl mx-auto px-5 sm:px-6 pt-12 sm:pt-14 pb-6 sm:pb-8">
          <div className="grid grid-cols-1 sm:grid-cols-12 gap-10 sm:gap-8 mb-10 sm:mb-12">
            {/* Brand */}
            <div className="sm:col-span-5">
              <div className="flex items-center gap-2.5 mb-3">
                <img
                  src="/icons/icon.svg"
                  alt=""
                  className="w-5 h-5 rounded-md"
                />
                <span className="text-sm font-bold tracking-tight text-stone-900 dark:text-stone-100 font-serif">
                  {APP_NAME}
                </span>
              </div>
              <p className="text-xs text-stone-400 dark:text-stone-500 leading-relaxed mb-4 max-w-xs">
                {t("landing.footerTagline")}
              </p>
              <a
                href={GITHUB_URL}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-2 rounded-lg border border-stone-200 dark:border-stone-700/40 bg-white dark:bg-stone-800/40 px-3 py-1.5 text-[11px] font-medium text-stone-500 dark:text-stone-400 hover:text-stone-900 dark:hover:text-stone-100 hover:border-stone-300 dark:hover:border-stone-600 transition-colors"
              >
                <GitHubIcon className="h-3 w-3" />
                GitHub
              </a>
            </div>

            {/* Link columns */}
            <div className="sm:col-span-7 grid grid-cols-3 gap-8 sm:gap-10">
              <div>
                <h4 className="text-[10px] font-semibold tracking-[0.1em] uppercase text-stone-400 dark:text-stone-500 mb-3">
                  {t("landing.coreFeatures")}
                </h4>
                <ul className="space-y-2">
                  {NAV_ITEMS.map((item) => (
                    <li key={item.id}>
                      <button
                        onClick={() => scrollToSection(item.id)}
                        className="text-xs text-stone-500 dark:text-stone-400 hover:text-stone-900 dark:hover:text-stone-100 transition-colors"
                      >
                        {t(`landing.${item.labelKey}`)}
                      </button>
                    </li>
                  ))}
                  <li>
                    <button
                      onClick={() => scrollToSection("responsive")}
                      className="text-xs text-stone-500 dark:text-stone-400 hover:text-stone-900 dark:hover:text-stone-100 transition-colors"
                    >
                      {t("landing.responsiveDesign")}
                    </button>
                  </li>
                </ul>
              </div>
              <div>
                <h4 className="text-[10px] font-semibold tracking-[0.1em] uppercase text-stone-400 dark:text-stone-500 mb-3">
                  Resources
                </h4>
                <ul className="space-y-2">
                  <li>
                    <a
                      href={GITHUB_URL}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-xs text-stone-500 dark:text-stone-400 hover:text-stone-900 dark:hover:text-stone-100 transition-colors inline-flex items-center gap-1.5"
                    >
                      <GitHubIcon className="h-3 w-3" /> GitHub
                    </a>
                  </li>
                  <li>
                    <a
                      href={GITHUB_URL}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-xs text-stone-500 dark:text-stone-400 hover:text-stone-900 dark:hover:text-stone-100 transition-colors"
                    >
                      MIT License
                    </a>
                  </li>
                </ul>
              </div>
              <div>
                <h4 className="text-[10px] font-semibold tracking-[0.1em] uppercase text-stone-400 dark:text-stone-500 mb-3">
                  {t("landing.footerBuiltWith")}
                </h4>
                <ul className="space-y-2">
                  {TECH_STACK.map((tech) => (
                    <li key={tech.labelKey}>
                      <span
                        className={`inline-flex items-center rounded-md px-2 py-0.5 text-[11px] font-medium ${tech.color}`}
                      >
                        {t(`landing.${tech.labelKey}`)}
                      </span>
                    </li>
                  ))}
                </ul>
              </div>
            </div>
          </div>

          {/* Bottom bar */}
          <div className="pt-5 sm:pt-6 border-t border-stone-200/60 dark:border-stone-800/40 flex flex-col sm:flex-row items-center justify-between gap-2">
            <span className="text-xs text-stone-400 dark:text-stone-500 font-serif">
              &copy; {new Date().getFullYear()} {APP_NAME}
            </span>
            <div className="flex items-center gap-1 text-xs text-stone-400 dark:text-stone-500">
              <span>Open Source</span>
              <span className="mx-1 text-stone-300 dark:text-stone-600">
                &middot;
              </span>
              <span>MIT</span>
            </div>
          </div>
        </div>
      </footer>

      {/* ── Back to top ── */}
      <button
        onClick={scrollToTop}
        className={`landing-back-top fixed bottom-5 right-5 sm:bottom-6 sm:right-6 z-40 w-10 h-10 rounded-xl bg-white dark:bg-stone-800 border border-stone-200/60 dark:border-stone-700/40 shadow-lg shadow-stone-200/30 dark:shadow-stone-900/40 flex items-center justify-center text-stone-400 dark:text-stone-500 hover:text-stone-700 dark:hover:text-stone-200 hover:bg-white dark:hover:bg-stone-700 hover:shadow-xl hover:-translate-y-0.5 transition-all duration-200 ${
          showBackTop
            ? "opacity-100 pointer-events-auto"
            : "opacity-0 pointer-events-none"
        }`}
        aria-label="Scroll to top"
      >
        <ArrowUpIcon />
      </button>

      {/* ── Image viewer ── */}
      <ImageViewer
        src={viewerSrc ?? ""}
        alt={viewerAlt}
        isOpen={!!viewerSrc}
        onClose={closeViewer}
      />
    </div>
  );
}

export default LandingPage;
