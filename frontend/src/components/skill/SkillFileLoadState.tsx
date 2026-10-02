import { useTranslation } from "react-i18next";
import { Button } from "../common";
import { LoadingSpinner } from "../common/LoadingSpinner";
import { ConfigPanelErrorCallout } from "../panels/ConfigPanelErrorCallout";

export function SkillFileLoadState({
  path,
  error,
  onRetry,
  className = "",
}: {
  path: string;
  error?: string;
  onRetry: () => void;
  className?: string;
}) {
  const { t } = useTranslation();
  return (
    <div
      className={`flex h-full flex-col items-center justify-center gap-3 p-3 ${className}`}
    >
      <span
        className="max-w-full truncate font-mono text-12 text-[var(--theme-text-secondary)]"
        title={path}
      >
        {path}
      </span>
      {error ? (
        <>
          <ConfigPanelErrorCallout message={error} />
          <Button onClick={onRetry} className="min-h-11">
            {t("common.retry")}
          </Button>
        </>
      ) : (
        <div
          role="status"
          className="flex items-center gap-2 text-14 text-[var(--theme-text-secondary)]"
        >
          <LoadingSpinner size="sm" />
          {t("common.loading")}
        </div>
      )}
    </div>
  );
}
