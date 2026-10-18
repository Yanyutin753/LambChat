import { useTranslation } from "react-i18next";
import { StatusBadge, type StatusColor } from "../../common/StatusBadge";

const STATUS_COLOR_MAP: Record<string, StatusColor> = {
  active: "emerald",
  paused: "stone",
};

/** Status badge for task status display */
export function StatusBadgeForTask({ status }: { status: string }) {
  const { t } = useTranslation();
  return (
    <StatusBadge
      color={STATUS_COLOR_MAP[status] ?? "stone"}
      label={t(`scheduledTask.${status}`)}
    />
  );
}

const RUN_STATUS_COLOR_MAP: Record<string, StatusColor> = {
  success: "emerald",
  failed: "red",
  running: "blue",
  waiting_human: "amber",
  pending: "stone",
  timeout: "amber",
  skipped: "stone",
};

/** Run status badge */
export function RunStatusBadge({ status }: { status: string }) {
  const { t } = useTranslation();
  const color = RUN_STATUS_COLOR_MAP[status] ?? "stone";

  return (
    <StatusBadge
      color={color}
      label={t(
        status === "waiting_human"
          ? "chat.goal.waiting_human"
          : `scheduledTask.${status}`,
      )}
      size="sm"
    />
  );
}
