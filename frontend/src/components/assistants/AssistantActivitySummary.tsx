import {
  CircleAlert,
  CircleCheck,
  Clock3,
  LoaderCircle,
  MessageCircle,
  Pause,
} from "lucide-react";
import { useTranslation } from "react-i18next";
import type { Assistant } from "../../types/assistant";

/** The roster and Chief share the same runtime status, separate from configuration. */
export function AssistantActivitySummary({
  assistant,
  fallback,
}: {
  assistant?: Assistant;
  fallback?: string;
}) {
  const { t } = useTranslation();
  const activity = assistant?.activity;
  const state = activity?.state;
  const busy =
    state &&
    ["running", "starting", "recovering", "cancelling"].includes(state);
  const attention = state === "waiting_human";
  const failed = state === "failed" || state === "expired";
  const Icon = attention
    ? MessageCircle
    : failed
      ? CircleAlert
      : busy
        ? LoaderCircle
        : state === "completed"
          ? CircleCheck
          : state === "cancelled"
            ? Pause
            : Clock3;
  return (
    <>
      <span className="block truncate font-medium">
        {assistant?.name || "Chief"}
      </span>
      <span className="assistant-workspace-role flex min-w-0 items-center gap-2">
        {activity && (
          <span
            className={`inline-flex shrink-0 items-center gap-1 text-12 ${
              attention
                ? "text-theme-primary"
                : failed
                  ? "text-theme-error"
                  : "text-theme-text-secondary"
            }`}
          >
            <Icon
              size={12}
              aria-hidden="true"
              className={
                busy ? "animate-spin motion-reduce:animate-none" : undefined
              }
            />
            {t(`assistants.activity.${state}`)}
          </span>
        )}
        <span className="truncate">
          {assistant && assistant.status !== "active"
            ? `${t(`assistants.${assistant.status}`)} · `
            : ""}
          {activity?.preview || fallback}
        </span>
      </span>
    </>
  );
}
