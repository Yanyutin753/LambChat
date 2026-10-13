import { useTranslation } from "react-i18next";
import { LoadingSpinner } from "./LoadingSpinner";

interface PanelLoadingStateProps {
  text?: string;
  containerClassName?: string;
  className?: string;
}

export function PanelLoadingState({
  text,
  containerClassName = "h-full",
  className = "",
}: PanelLoadingStateProps) {
  const { t } = useTranslation();
  return (
    <div
      role="status"
      aria-live="polite"
      aria-label={text ? undefined : t("common.loading")}
      className={`flex ${containerClassName} items-center justify-center p-6 ${className}`}
    >
      <div className="flex min-w-0 flex-col items-center gap-3 text-center">
        <div className="flex justify-center">
          <LoadingSpinner size="md" color="text-theme-text-tertiary" />
        </div>
        {text ? (
          <p className="loading-label text-14 text-theme-text-secondary break-words">
            {text}
          </p>
        ) : null}
      </div>
    </div>
  );
}
