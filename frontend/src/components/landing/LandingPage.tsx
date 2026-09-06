import { useEffect, useState, useCallback, useMemo } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { ImageViewer } from "../common/ImageViewer";
import { useAuth } from "../../hooks/useAuth";
import { getAccessToken } from "../../services/api/token";
import { useSEO } from "../../hooks/usePageTitle";
import { AutoLoginSplash } from "./AutoLoginSplash";
import { shouldShowAutoLoginSplash } from "./autoLoginGate";
import { useScrollReveal } from "./hooks/useScrollReveal";
import { useScrollProgress } from "./hooks/useScrollProgress";
import { useActiveSection } from "./hooks/useActiveSection";
import {
  SECTION_ID_BY_ROUTE,
  SECTION_IDS,
  SECTION_ROUTE_BY_ID,
} from "./constants";
import { MAIN_SHOTS, MGMT_SHOTS, RESPONSIVE_SHOTS } from "./data";
import { Navbar } from "./components/Navbar";
import { MobileMenu } from "./components/MobileMenu";
import { HeroSection } from "./components/HeroSection";
import { InterfaceSection } from "./components/InterfaceSection";
import { FeaturesSection } from "./components/FeaturesSection";
import { ArchitectureSection } from "./components/ArchitectureSection";
import { DashboardSection } from "./components/DashboardSection";
import { ResponsiveSection } from "./components/ResponsiveSection";
import { CTASection } from "./components/CTASection";
import { Footer } from "./components/Footer";
import { ScrollButtons } from "./components/ScrollButtons";

export function LandingPage() {
  const location = useLocation();
  const currentSectionId = SECTION_ID_BY_ROUTE[location.pathname];
  const seoPath =
    currentSectionId || location.pathname === "/github"
      ? location.pathname
      : "/";

  useSEO({
    title: "seo.landing.title",
    description: "seo.landing.description",
    path: seoPath,
    omitSuffix: true,
  });
  const navigate = useNavigate();
  const { t, i18n } = useTranslation();
  const containerRef = useScrollReveal();
  const { isAuthenticated, isLoading, token } = useAuth();
  const scrollProgress = useScrollProgress();
  const activeSection = useActiveSection(SECTION_IDS);
  const [showBackTop, setShowBackTop] = useState(false);
  const [showScrollBottom, setShowScrollBottom] = useState(true);
  const [showNav, setShowNav] = useState(false);
  const [scrolled, setScrolled] = useState(false);
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const [viewerIndex, setViewerIndex] = useState<number | null>(null);

  const galleryItems = useMemo(
    () => [
      ...MAIN_SHOTS.map((s) => ({ src: s.src, alt: t(`landing.${s.altKey}`) })),
      {
        src: "/images/best-practice/architecture.webp",
        alt: t("landing.architecture"),
      },
      ...MGMT_SHOTS.map((s) => ({ src: s.src, alt: t(`landing.${s.altKey}`) })),
      ...RESPONSIVE_SHOTS.map((s) => ({
        src: s.src,
        alt: t(`landing.${s.altKey}`),
      })),
    ],
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [i18n.language],
  );

  const openViewer = useCallback(
    (src: string, _alt: string) => {
      const idx = galleryItems.findIndex((item) => item.src === src);
      setViewerIndex(idx >= 0 ? idx : null);
      setMobileMenuOpen(false);
    },
    [galleryItems],
  );
  const closeViewer = useCallback(() => setViewerIndex(null), []);

  useEffect(() => {
    if (!isLoading && isAuthenticated) navigate("/chat", { replace: true });
  }, [isLoading, isAuthenticated, navigate]);

  useEffect(() => {
    document.documentElement.classList.add("allow-scroll");
    return () => document.documentElement.classList.remove("allow-scroll");
  }, []);

  useEffect(() => {
    const h = () => {
      const y = window.scrollY;
      const max = document.documentElement.scrollHeight - window.innerHeight;
      setShowBackTop(y > 600);
      setShowNav(y > 300);
      setShowScrollBottom(y < max - 600);
      setScrolled(y > 10);
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
    // If already authenticated, or auth is still loading (token may still be valid),
    // navigate directly to chat instead of the login page
    if (isAuthenticated || (isLoading && getAccessToken())) {
      navigate("/chat");
    } else {
      navigate("/auth/login");
    }
  }, [navigate, isAuthenticated, isLoading]);

  const scrollToSection = useCallback(
    (id: string) => {
      setMobileMenuOpen(false);
      const route = SECTION_ROUTE_BY_ID[id];
      if (route && window.location.pathname !== route) {
        navigate(route, { replace: false });
      }
      document.getElementById(id)?.scrollIntoView({ behavior: "smooth" });
    },
    [navigate],
  );

  useEffect(() => {
    if (!currentSectionId) return;

    window.requestAnimationFrame(() => {
      document
        .getElementById(currentSectionId)
        ?.scrollIntoView({ behavior: "auto" });
    });
  }, [currentSectionId]);

  const scrollToTop = useCallback(
    () => window.scrollTo({ top: 0, behavior: "smooth" }),
    [],
  );

  const scrollToBottom = useCallback(
    () =>
      window.scrollTo({
        top: document.documentElement.scrollHeight,
        behavior: "smooth",
      }),
    [],
  );

  // 已登录用户停在 / 时鉴权尚未落地——先显示品牌过渡页，
  // 避免整个营销落地页闪现后再被跳去 /chat（放在全部 hooks 之后）
  if (
    shouldShowAutoLoginSplash({
      isLoading,
      isAuthenticated,
      hasToken: !!token,
    })
  ) {
    return <AutoLoginSplash />;
  }

  return (
    <div
      ref={containerRef}
      className="blog-landing-container font-serif relative bg-white dark:bg-stone-950 antialiased"
    >
      {/* Progress bar */}
      <div
        className="landing-progress-bar"
        style={{ width: `${scrollProgress}%` }}
      />

      <Navbar
        activeSection={activeSection}
        showNav={showNav}
        scrolled={scrolled}
        mobileMenuOpen={mobileMenuOpen}
        onToggleMobileMenu={() => setMobileMenuOpen(!mobileMenuOpen)}
        onScrollToSection={scrollToSection}
      />

      {mobileMenuOpen && (
        <MobileMenu
          activeSection={activeSection}
          onClose={() => setMobileMenuOpen(false)}
          onScrollToSection={scrollToSection}
        />
      )}

      <HeroSection onLogin={goLogin} />

      <div className="blog-section-divider py-2" aria-hidden="true">
        <div className="blog-ornament-diamond" />
      </div>

      <InterfaceSection onOpenViewer={openViewer} />

      <div className="blog-section-divider py-2" aria-hidden="true">
        <div className="blog-ornament-diamond" />
      </div>

      <FeaturesSection />

      <div className="blog-section-divider py-2" aria-hidden="true">
        <div className="blog-ornament-diamond" />
      </div>

      <ArchitectureSection onOpenViewer={openViewer} />

      <div className="blog-section-divider py-2" aria-hidden="true">
        <div className="blog-ornament-diamond" />
      </div>

      <DashboardSection onOpenViewer={openViewer} />

      <div className="blog-section-divider py-2" aria-hidden="true">
        <div className="blog-ornament-diamond" />
      </div>

      <ResponsiveSection onOpenViewer={openViewer} />

      <CTASection onLogin={goLogin} />

      <Footer onScrollToSection={scrollToSection} />

      <ScrollButtons
        showTop={showBackTop}
        showBottom={showScrollBottom}
        onScrollToTop={scrollToTop}
        onScrollToBottom={scrollToBottom}
      />

      <ImageViewer
        src={viewerIndex !== null ? galleryItems[viewerIndex].src : ""}
        alt={viewerIndex !== null ? galleryItems[viewerIndex].alt : ""}
        isOpen={viewerIndex !== null}
        onClose={closeViewer}
        onPrevious={() =>
          setViewerIndex((i) => (i !== null && i > 0 ? i - 1 : i))
        }
        onNext={() =>
          setViewerIndex((i) =>
            i !== null && i < galleryItems.length - 1 ? i + 1 : i,
          )
        }
        hasPrevious={viewerIndex !== null && viewerIndex > 0}
        hasNext={viewerIndex !== null && viewerIndex < galleryItems.length - 1}
        positionLabel={
          viewerIndex !== null
            ? `${viewerIndex + 1} / ${galleryItems.length}`
            : undefined
        }
      />
    </div>
  );
}

export default LandingPage;
