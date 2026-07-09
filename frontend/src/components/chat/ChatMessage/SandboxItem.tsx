import { useState } from "react";
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
  const [isExpanded, setIsExpanded] = useState(false);

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
    (status === "error" && error) ||
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
            : t("chat.sandbox.name")
      }
      expandable={!!hasDetails}
      onExpandChange={setIsExpanded}
      animatedDots={status === "starting"}
    >
      {isExpanded && hasDetails && (
        <div className="mt-1 ml-4 pl-3 border-l-2 border-theme-border max-h-40 overflow-y-auto">
          {status === "ready" && (
            <div className="text-xs text-theme-text pl-1 py-0.5 font-mono flex items-center gap-1.5">
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
            <div className="text-xs text-red-600 dark:text-red-400 pl-1 py-0.5">
              {error || t("chat.sandboxInitFailed")}
              {durationText &&
                ` · ${t("chat.sandbox.elapsed", { duration: durationText })}`}
            </div>
          )}
          {status === "cancelled" && (
            <div className="text-xs text-amber-600 dark:text-amber-400 pl-1 py-1">
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
