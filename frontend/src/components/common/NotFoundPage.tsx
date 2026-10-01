import { Link } from "react-router-dom";
import { Home } from "lucide-react";
import { useTranslation } from "react-i18next";
import { usePageTitle } from "../../hooks/usePageTitle";
import { SceneIllustration } from "./SceneIllustration";

export function NotFoundPage() {
  usePageTitle("404");
  const { t } = useTranslation();

  return (
    <main className="safe-area-viewport-padding flex min-h-[calc(100dvh-var(--titlebar-inset,0px))] w-full items-center justify-center bg-theme-bg px-6 py-16">
      <div className="flex max-w-md flex-col items-center text-center">
        <SceneIllustration scene="message" className="mb-6" />
        <h1 className="mb-4 text-30 font-medium font-serif leading-snug text-theme-text">
          {t("errors.pageNotFound")}
        </h1>
        <p className="mb-8 text-15 leading-relaxed text-theme-text-secondary">
          {t("errors.pageNotFoundDesc")}
        </p>
        <Link
          to="/chat"
          className="inline-flex min-h-12 items-center gap-2 rounded-lg bg-theme-text px-6 py-3 text-14 font-medium text-theme-bg transition-colors hover:bg-theme-text-secondary focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-theme-primary"
        >
          <Home size={18} aria-hidden="true" />
          {t("errors.backToHome")}
        </Link>
      </div>
    </main>
  );
}
