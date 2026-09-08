import { useTranslation } from "react-i18next";
import { clsx } from "clsx";
import { CalendarClock, TerminalSquare, Check, Minus, Bot } from "lucide-react";

interface ScheduledTaskApprovalContentProps {
  preview: {
    name: string;
    agent_id: string;
    schedule: string;
    run_on_start: boolean;
    timeout_seconds: number;
    message: string;
  };
}

function SpecRow({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <div className="approval-st-row">
      <span className="approval-st-label">{label}</span>
      <span className="approval-st-value">{children}</span>
    </div>
  );
}

function MonoChip({ children }: { children: React.ReactNode }) {
  return <code className="approval-st-mono">{children}</code>;
}

/**
 * Renders a scheduled task creation approval as a compact spec sheet:
 * definition rows for the task parameters plus a code block for the run
 * prompt. Used by ApprovalPanel when an approval has
 * metadata.approval_type === "scheduled_task_create".
 */
export function ScheduledTaskApprovalContent({
  preview,
}: ScheduledTaskApprovalContentProps) {
  const { t } = useTranslation();

  return (
    <div className="approval-st">
      <p className="approval-st-lead">
        {t("approvals.scheduledTask.confirmCreation")}
      </p>
      <p className="approval-st-note">
        {t("approvals.scheduledTask.noTaskYet")}
      </p>

      <div className="approval-st-sheet">
        <SpecRow label={t("approvals.scheduledTask.name")}>
          <span className="approval-st-name">{preview.name}</span>
        </SpecRow>
        <SpecRow label={t("approvals.scheduledTask.agent")}>
          <MonoChip>
            <Bot
              size={11}
              strokeWidth={2}
              aria-hidden="true"
              className="approval-st-chip-icon"
            />
            {preview.agent_id}
          </MonoChip>
        </SpecRow>
        <SpecRow label={t("approvals.scheduledTask.schedule")}>
          <MonoChip>
            <CalendarClock
              size={11}
              strokeWidth={2}
              aria-hidden="true"
              className="approval-st-chip-icon"
            />
            {preview.schedule}
          </MonoChip>
        </SpecRow>
        <SpecRow label={t("approvals.scheduledTask.runImmediately")}>
          <span
            className={clsx(
              "approval-st-flag",
              preview.run_on_start
                ? "approval-st-flag--on"
                : "approval-st-flag--off",
            )}
          >
            {preview.run_on_start ? (
              <Check size={11} strokeWidth={2.5} aria-hidden="true" />
            ) : (
              <Minus size={11} strokeWidth={2.5} aria-hidden="true" />
            )}
            {preview.run_on_start
              ? t("approvals.scheduledTask.yes")
              : t("approvals.scheduledTask.no")}
          </span>
        </SpecRow>
        <SpecRow label={t("approvals.scheduledTask.timeout")}>
          <MonoChip>{preview.timeout_seconds}s</MonoChip>
        </SpecRow>
      </div>

      <p className="approval-st-effect">
        {t("approvals.scheduledTask.effect", {
          agent: preview.agent_id,
          schedule: preview.schedule,
        })}
        {preview.run_on_start && t("approvals.scheduledTask.effectImmediate")}
      </p>

      <div className="approval-st-prompt">
        <div className="approval-st-prompt-header">
          <TerminalSquare size={12} strokeWidth={2} aria-hidden="true" />
          <span>{t("approvals.scheduledTask.promptSent")}</span>
        </div>
        <pre className="approval-st-prompt-body">
          <code>{preview.message}</code>
        </pre>
      </div>
    </div>
  );
}
