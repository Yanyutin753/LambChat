import { Link } from "react-router-dom";
import { ThemeToggle } from "../common/ThemeToggle";
import { LanguageToggle } from "../common/LanguageToggle";
import { APP_NAME } from "../../constants";

interface AuthLayoutProps {
  children: React.ReactNode;
}

export function AuthLayout({ children }: AuthLayoutProps) {
  return (
    <div className="auth-shell min-h-screen overflow-y-auto overflow-x-hidden">
      <div className="auth-crosshatch" aria-hidden="true" />
      <div className="auth-atmosphere" aria-hidden="true">
        <div className="absolute top-0 left-1/2 -translate-x-1/2 w-[700px] h-[500px] bg-[radial-gradient(ellipse_at_center,rgba(251,191,36,0.06)_0%,rgba(251,146,60,0.025)_40%,transparent_70%)] dark:bg-[radial-gradient(ellipse_at_center,rgba(251,191,36,0.035)_0%,rgba(251,146,60,0.015)_40%,transparent_70%)]" />
        <div className="absolute top-[30%] left-[5%] w-[350px] h-[350px] bg-[radial-gradient(circle,rgba(56,189,248,0.035)_0%,transparent_60%)] dark:bg-[radial-gradient(circle,rgba(56,189,248,0.025)_0%,transparent_60%)]" />
        <div className="absolute bottom-[15%] right-[10%] w-[280px] h-[280px] bg-[radial-gradient(circle,rgba(168,85,247,0.03)_0%,transparent_60%)] dark:bg-[radial-gradient(circle,rgba(168,85,247,0.018)_0%,transparent_60%)]" />
      </div>

      <nav className="fixed top-0 inset-x-0 z-50 bg-white/90 dark:bg-stone-950/90 border-b border-stone-100/60 dark:border-stone-800/40 transition-shadow duration-300">
        <div className="max-wfull mx-auto px-5 sm:px-8 h-14 flex items-center justify-between">
          <Link to="/" className="flex items-center gap-2.5 group">
            <img
              src="/icons/icon.svg"
              alt={APP_NAME}
              className="w-6 h-6 sm:w-7 sm:h-7 rounded-lg transition-transform duration-300 group-hover:scale-105"
            />
            <span className="text-[15px] sm:text-lg font-bold tracking-tight text-stone-900 dark:text-stone-100 font-serif">
              {APP_NAME}
            </span>
          </Link>
          <div className="flex items-center gap-1.5">
            <LanguageToggle />
            <ThemeToggle />
          </div>
        </div>
      </nav>

      <div className="relative z-10 flex min-h-screen items-center justify-center px-4 py-6 sm:px-6">
        <div className="w-full max-w-[350px] sm:max-w-[450px]">{children}</div>
      </div>
    </div>
  );
}
