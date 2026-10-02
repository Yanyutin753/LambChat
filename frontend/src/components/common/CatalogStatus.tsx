import type { RefObject } from "react";
import { useTranslation } from "react-i18next";
import { AlertCircle } from "lucide-react";
import { LoadingSpinner } from "./LoadingSpinner";
import { Button } from "./ui/Button";

/** Inline catalog feedback shared by settings and member configuration. */
export function CatalogStatus({
  label,
  loading,
  error,
  onRetry,
  focusTargetRef,
  loadingText,
  errorText,
  disabled = false,
}: {
  label: string;
  loading?: boolean;
  error?: boolean;
  onRetry: () => void;
  focusTargetRef: RefObject<HTMLElement | null>;
  loadingText?: string;
  errorText?: string;
  disabled?: boolean;
}) {
  const { t } = useTranslation();
  if (!loading && !error) return null;
  return (
    <div className="flex min-w-0 flex-wrap items-center gap-x-2 gap-y-1 text-12 text-theme-text-secondary">
      <span
        role={loading ? "status" : "alert"}
        className="flex min-w-0 items-center gap-2 [overflow-wrap:anywhere]"
      >
        {loading ? (
          <LoadingSpinner size="sm" />
        ) : (
          <AlertCircle
            size={14}
            className="shrink-0 text-theme-error"
            aria-hidden="true"
          />
        )}
        {label} ·{" "}
        {loading
          ? (loadingText ?? t("common.loading"))
          : (errorText ?? t("common.loadFailed"))}
      </span>
      {!loading && (
        <Button
          variant="ghost"
          size="sm"
          disabled={disabled}
          aria-label={`${t("common.retry")}: ${label}`}
          className="max-sm:!min-h-11 [@media(pointer:coarse)]:!min-h-11"
          onClick={() => {
            focusTargetRef.current?.focus({ preventScroll: true });
            onRetry();
          }}
        >
          {t("common.retry")}
        </Button>
      )}
    </div>
  );
}
