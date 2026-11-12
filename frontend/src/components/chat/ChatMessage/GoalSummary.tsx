import { useTranslation } from "react-i18next";

/** Shared with the original Goal popover so tool details keep the same hierarchy. */
export function GoalSummary({
  objective,
  statusLabel,
}: {
  objective?: string;
  statusLabel: string;
}) {
  const { t } = useTranslation();
  return (
    <div className="min-w-0">
      <div className="mb-2 flex items-start justify-between gap-2">
        <span className="text-12 font-medium text-theme-primary">
          {t("chat.goal.active")}
        </span>
        <span className="rounded-full bg-theme-primary/10 px-1.5 py-0.5 text-12 font-medium text-theme-primary">
          {statusLabel}
        </span>
      </div>
      {objective && (
        <p className="whitespace-pre-wrap text-14 leading-relaxed text-theme-text [overflow-wrap:anywhere]">
          {objective}
        </p>
      )}
    </div>
  );
}
