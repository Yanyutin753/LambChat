import { useTranslation } from "react-i18next";

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

/**
 * Renders a scheduled task creation approval with i18n support.
 * Used by ApprovalPanel when an approval has metadata.approval_type === "scheduled_task_create".
 */
export function ScheduledTaskApprovalContent({
  preview,
}: ScheduledTaskApprovalContentProps) {
  const { t } = useTranslation();

  const immediate = preview.run_on_start
    ? `✅ ${t("approvals.scheduledTask.yes")}`
    : `❌ ${t("approvals.scheduledTask.no")}`;

  return (
    <div>
      <p>{t("approvals.scheduledTask.confirmCreation")}</p>
      <p>{t("approvals.scheduledTask.noTaskYet")}</p>

      <table>
        <thead>
          <tr>
            <th></th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          <tr>
            <td>
              <strong>{t("approvals.scheduledTask.name")}</strong>
            </td>
            <td>{preview.name}</td>
          </tr>
          <tr>
            <td>
              <strong>{t("approvals.scheduledTask.agent")}</strong>
            </td>
            <td>
              <code>{preview.agent_id}</code>
            </td>
          </tr>
          <tr>
            <td>
              <strong>{t("approvals.scheduledTask.schedule")}</strong>
            </td>
            <td>{preview.schedule}</td>
          </tr>
          <tr>
            <td>
              <strong>{t("approvals.scheduledTask.runImmediately")}</strong>
            </td>
            <td>{immediate}</td>
          </tr>
          <tr>
            <td>
              <strong>{t("approvals.scheduledTask.timeout")}</strong>
            </td>
            <td>{preview.timeout_seconds}s</td>
          </tr>
        </tbody>
      </table>

      <p>
        {t("approvals.scheduledTask.effect", {
          agent: preview.agent_id,
          schedule: preview.schedule,
        })}
        {preview.run_on_start && t("approvals.scheduledTask.effectImmediate")}
      </p>

      <p>
        <strong>{t("approvals.scheduledTask.promptSent")}</strong>
      </p>
      <pre className="max-h-48 overflow-y-auto whitespace-pre-wrap break-words">
        <code>{preview.message}</code>
      </pre>
    </div>
  );
}
