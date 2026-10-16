import { Box } from "lucide-react";
import { useTranslation } from "react-i18next";
import { CollapsiblePill } from "../../common";
import type { CollapsibleStatus } from "../../common";
import { formatDuration } from "../../../utils/datetime";

export function SandboxItem({
  status,
  sandboxId,
  error,
  startedAt,
  completedAt,
}: {
  status: "starting" | "ready" | "error" | "cancelled";
  sandboxId?: string;
  error?: string;
  startedAt?: string;
  completedAt?: string;
}) {
  const { t } = useTranslation();

  const durationText = (() => {
    if (startedAt) {
      const startMs = new Date(startedAt).getTime();
      const endMs = completedAt
        ? new Date(completedAt).getTime()
        : status !== "starting"
          ? Date.now()
          : undefined;
      if (endMs != null && endMs > startMs) {
        return formatDuration(endMs - startMs);
      }
    }
    return undefined;
  })();

  const hasDetails =
    (status === "ready" && (sandboxId || durationText)) ||
    status === "error" ||
    status === "cancelled";

  const pillStatus: CollapsibleStatus =
    status === "starting"
      ? "loading"
      : status === "ready"
        ? "success"
        : status === "cancelled"
          ? "cancelled"
          : "error";

  return (
    <CollapsiblePill
      status={pillStatus}
      icon={<Box size={12} className="shrink-0 opacity-50" />}
      label={
        status === "starting"
          ? t("chat.sandbox.initializing")
          : status === "ready"
            ? t("chat.sandbox.ready")
            : status === "error"
              ? t("chat.sandboxInitFailed")
              : `${t("chat.sandbox.name")} · ${t("chat.cancelled")}`
      }
      formatLabel={false}
      suffix={
        status === "ready" && sandboxId ? (
          <span className="min-w-0 truncate">
            {t("chat.sandboxId", { id: sandboxId })}
          </span>
        ) : undefined
      }
      expandable={!!hasDetails}
      animatedDots={status === "starting"}
    >
      {hasDetails && (
        <div
          className="mt-1 ml-4 pl-3 border-l-2 border-theme-border max-h-40 overflow-y-auto break-words [overflow-wrap:anywhere] focus-visible:outline focus-visible:outline-2 focus-visible:outline-[var(--theme-ring)]"
          tabIndex={0}
        >
          {status === "ready" && (
            <div className="text-12 text-theme-text pl-1 py-0.5 font-mono flex items-center gap-1.5">
              {sandboxId && (
                <span>{t("chat.sandboxId", { id: sandboxId })}</span>
              )}
              {durationText && (
                <span>
                  {t("chat.sandbox.elapsed", { duration: durationText })}
                </span>
              )}
            </div>
          )}
          {status === "error" && (
            <div className="text-12 text-[color-mix(in_srgb,var(--theme-error)_45%,var(--theme-text))] pl-1 py-0.5">
              {error || t("chat.sandboxInitFailed")}
              {durationText &&
                ` · ${t("chat.sandbox.elapsed", { duration: durationText })}`}
            </div>
          )}
          {status === "cancelled" && (
            <div className="text-12 text-theme-text-tertiary pl-1 py-1">
              {t("chat.cancelled")}
              {durationText &&
                ` · ${t("chat.sandbox.elapsed", { duration: durationText })}`}
            </div>
          )}
        </div>
      )}
    </CollapsiblePill>
  );
}
