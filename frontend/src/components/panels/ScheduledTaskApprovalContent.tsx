import { useTranslation } from "react-i18next";
import { AgentIcon } from "../agent/AgentIcon";
import { useAgentCatalog } from "../agent/useAgentCatalog";
import { resolveAgentReferenceName } from "../agent/agentCatalog";
import { clsx } from "clsx";
import { CalendarClock, Check, Minus } from "lucide-react";

interface ScheduledTaskApprovalContentProps {
  preview: {
    name: string;
    agent_id: string;
    schedule: string;
    run_on_start: boolean;
    timeout_seconds: number;
    message: string;
    execution_mode?: "conversation" | "standalone";
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
      <dt className="approval-st-label">{label}</dt>
      <dd className="approval-st-value">{children}</dd>
    </div>
  );
}

function ParameterValue({ children }: { children: React.ReactNode }) {
  return <span className="approval-st-parameter">{children}</span>;
}

/**
 * Renders a scheduled task creation approval as a compact spec sheet:
 * definition rows for the task parameters plus plain text for the run
 * prompt. Used by ApprovalPanel when an approval has
 * metadata.approval_type === "scheduled_task_create".
 */
export function ScheduledTaskApprovalContent({
  preview,
}: ScheduledTaskApprovalContentProps) {
  const { t, i18n } = useTranslation();
  const agents = useAgentCatalog();
  const agentName = resolveAgentReferenceName(
    preview.agent_id,
    "",
    agents,
    i18n.language,
    t,
  );

  return (
    <div className="approval-st">
      <p className="approval-st-note">
        {t("approvals.scheduledTask.noTaskYet")}
      </p>

      <dl className="approval-st-sheet">
        <SpecRow label={t("approvals.scheduledTask.name")}>
          <span className="approval-st-name">{preview.name}</span>
        </SpecRow>
        <SpecRow label={t("scheduledTask.executionMode")}>
          {t(
            preview.execution_mode === "conversation"
              ? "scheduledTask.conversationMode"
              : "scheduledTask.standaloneMode",
          )}
        </SpecRow>
        <SpecRow label={t("approvals.scheduledTask.agent")}>
          <ParameterValue>
            <AgentIcon
              icon={agents.find((agent) => agent.id === preview.agent_id)?.icon}
              seed={preview.agent_id}
              size={14}
              className="approval-st-chip-icon"
            />
            {agentName}
          </ParameterValue>
        </SpecRow>
        <SpecRow label={t("approvals.scheduledTask.schedule")}>
          <ParameterValue>
            <CalendarClock
              size={11}
              strokeWidth={2}
              aria-hidden="true"
              className="approval-st-chip-icon"
            />
            {preview.schedule}
          </ParameterValue>
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
      </dl>

      <p className="approval-st-effect">
        {t(
          preview.execution_mode === "conversation"
            ? "approvals.scheduledTask.conversationSummary"
            : "approvals.scheduledTask.standaloneSummary",
        )}
      </p>

      <div className="approval-st-prompt">
        <div className="approval-st-prompt-header">
          <span>{t("approvals.scheduledTask.promptSent")}</span>
        </div>
        <p className="approval-st-prompt-body">{preview.message}</p>
      </div>
    </div>
  );
}
