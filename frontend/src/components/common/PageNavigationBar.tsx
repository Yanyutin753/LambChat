import type { ReactNode } from "react";
import { ChevronLeft } from "lucide-react";
import { useTranslation } from "react-i18next";
import { ToolbarIconButton } from "./ui/ToolbarIconButton";

interface PageNavigationBarProps {
  title: string;
  onBack: () => void;
  icon?: ReactNode;
  actions?: ReactNode;
}

export function PageNavigationBar({
  title,
  onBack,
  icon,
  actions,
}: PageNavigationBarProps) {
  const { t } = useTranslation();

  return (
    <nav aria-label={title} className="flex min-w-0 flex-1 items-center gap-3">
      <div className="flex min-w-0 items-center gap-1.5 sm:gap-3">
        <ToolbarIconButton
          onClick={onBack}
          aria-label={t("common.back")}
          title={t("common.back")}
          className="hidden sm:flex"
          icon={<ChevronLeft size={18} aria-hidden="true" />}
        />
        <span
          aria-hidden="true"
          className="hidden h-4 w-px shrink-0 bg-theme-border sm:block"
        />
        <span className="shrink-0 sm:hidden">{icon}</span>
        <h1
          title={title}
          className="min-w-0 truncate text-16 font-semibold font-serif leading-5 text-theme-text"
        >
          {title}
        </h1>
      </div>
      <div className="ml-auto shrink-0">{actions}</div>
    </nav>
  );
}
