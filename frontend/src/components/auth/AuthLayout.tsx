import { Link } from "react-router-dom";
import { ThemeToggle } from "../common/ThemeToggle";
import { LanguageToggle } from "../common/LanguageToggle";
import { BrandWordmark } from "../common/BrandWordmark";
import { BrandLogo } from "../common/BrandLogo";
import { APP_NAME } from "../../constants";
import { useMobileKeyboardAware } from "../../hooks/useMobileKeyboardAware";

interface AuthLayoutProps {
  children: React.ReactNode;
}

export function AuthLayout({ children }: AuthLayoutProps) {
  const isKeyboardOpen = useMobileKeyboardAware();

  return (
    <div className="auth-shell min-h-[calc(100svh-var(--titlebar-inset,0px))] min-h-[calc(100dvh-var(--titlebar-inset,0px))] overflow-y-auto overflow-x-hidden">
      <div className="auth-crosshatch" aria-hidden="true" />
      <div className="auth-atmosphere" aria-hidden="true">
        <div className="auth-glow-main absolute top-0 left-1/2 -translate-x-1/2 w-[700px] h-[500px] bg-[radial-gradient(ellipse_at_center,rgba(251,191,36,0.06)_0%,rgba(251,146,60,0.025)_40%,transparent_70%)] dark:bg-[radial-gradient(ellipse_at_center,rgba(251,191,36,0.035)_0%,rgba(251,146,60,0.015)_40%,transparent_70%)]" />
        <div className="auth-glow-blue absolute top-[30%] left-[5%] w-[350px] h-[350px] bg-[radial-gradient(circle,rgba(56,189,248,0.035)_0%,transparent_60%)] dark:bg-[radial-gradient(circle,rgba(56,189,248,0.025)_0%,transparent_60%)]" />
        <div className="auth-glow-violet absolute bottom-[15%] right-[10%] w-[280px] h-[280px] bg-[radial-gradient(circle,rgba(168,85,247,0.03)_0%,transparent_60%)] dark:bg-[radial-gradient(circle,rgba(168,85,247,0.018)_0%,transparent_60%)]" />
      </div>

      <nav className="fixed top-0 inset-x-0 z-50 bg-white/90 dark:bg-stone-950/90 border-b border-stone-100/60 dark:border-stone-800/40 transition-shadow duration-300">
        <div className="mx-auto flex h-14 max-w-full items-center justify-between px-4 sm:px-8">
          <Link to="/" className="flex items-center group  gap-1.5">
            <BrandLogo
              alt={APP_NAME}
              className="h-8 transition-transform duration-300 group-hover:scale-105"
            />
            <BrandWordmark
              decorative
              className="w-auto text-stone-900 dark:text-stone-100 h-8"
            />
          </Link>
          <div className="flex items-center gap-1.5">
            <LanguageToggle />
            <ThemeToggle />
          </div>
        </div>
      </nav>

      <div
        className={`relative z-10 flex min-h-[calc(100svh-var(--titlebar-inset,0px))] min-h-[calc(100dvh-var(--titlebar-inset,0px))] justify-center px-4 sm:px-6 ${
          isKeyboardOpen
            ? "items-start pt-16 sm:pt-20"
            : "items-center py-20 sm:py-24"
        }`}
      >
        <div className="w-full max-w-[22.5rem] sm:max-w-[450px]">
          {children}
        </div>
      </div>
    </div>
  );
}
