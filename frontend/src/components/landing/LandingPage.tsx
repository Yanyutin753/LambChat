import { useEffect, useState, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { ImageViewer } from "../common/ImageViewer";
import { useAuth } from "../../hooks/useAuth";
import { useScrollReveal } from "./hooks/useScrollReveal";
import { useScrollProgress } from "./hooks/useScrollProgress";
import { useActiveSection } from "./hooks/useActiveSection";
import { SECTION_IDS } from "./constants";
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
  const navigate = useNavigate();
  const containerRef = useScrollReveal();
  const { isAuthenticated, isLoading } = useAuth();
  const scrollProgress = useScrollProgress();
  const activeSection = useActiveSection(SECTION_IDS);
  const [showBackTop, setShowBackTop] = useState(false);
  const [showScrollBottom, setShowScrollBottom] = useState(true);
  const [showNav, setShowNav] = useState(false);
  const [scrolled, setScrolled] = useState(false);
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

  const scrollToBottom = useCallback(
    () =>
      window.scrollTo({
        top: document.documentElement.scrollHeight,
        behavior: "smooth",
      }),
    [],
  );

  return (
    <div ref={containerRef} className="bg-white dark:bg-stone-950 antialiased">
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
        src={viewerSrc ?? ""}
        alt={viewerAlt}
        isOpen={!!viewerSrc}
        onClose={closeViewer}
      />
    </div>
  );
}

export default LandingPage;
