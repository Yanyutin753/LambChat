import { memo } from "react";
import { Target } from "lucide-react";
import { useTranslation } from "react-i18next";
import { CollapsiblePill } from "../../../common";
import { ToolDurationFooter } from "./ToolDurationFooter";
import { GoalSummary } from "../GoalSummary";
import { extractText } from "./toolUtils";
import { parseSubagentControlResult } from "../subagentPanelState";
import {
  openToolLivePanel,
  toolDetailPropsFromPanelData,
  type ToolDetailProps,
} from "./ToolLivePanelContent";

function GoalDetail({
  args,
  result,
  isPending,
  cancelled,
  success,
}: ToolDetailProps) {
  const { t } = useTranslation();
  const parsed = parseSubagentControlResult(result);
  const objective =
    typeof parsed?.objective === "string" ? parsed.objective : undefined;
  const rubric = typeof parsed?.rubric === "string" ? parsed.rubric : undefined;
  const explanation =
    typeof args.explanation === "string" ? args.explanation : undefined;
  const isAudit = ["complete", "blocked", "paused"].includes(
    String(args.status),
  );
  const failed = success === false || parsed?.status === "error";
  const goalStatus =
    typeof parsed?.status === "string" &&
    [
      "active",
      "paused",
      "waiting_human",
      "blocked",
      "completed",
      "budget_limited",
      "cleared",
    ].includes(parsed.status)
      ? parsed.status
      : undefined;
  const statusLabel = isPending
    ? t("common.loading")
    : cancelled
      ? t("chat.cancelled")
      : failed
        ? t("chat.message.error")
        : goalStatus
          ? t(`chat.goalPersistent.status.${goalStatus}`)
          : isAudit
            ? t("chat.goal.auditPending")
            : t("chat.goalPersistent.noGoal");
  const error =
    typeof parsed?.error === "string" ? parsed.error : extractText(result);
  return (
    <div className="tool-panel-content min-w-0 space-y-4 overflow-y-auto p-3 sm:p-4">
      <GoalSummary objective={objective} statusLabel={statusLabel} />
      {rubric && (
        <section className="space-y-1 border-t border-theme-border pt-3">
          <h3 className="text-12 font-medium text-theme-text-secondary">
            {t("chat.goalPersistent.criteria")}
          </h3>
          <p className="whitespace-pre-wrap text-14 leading-relaxed text-theme-text [overflow-wrap:anywhere]">
            {rubric}
          </p>
        </section>
      )}
      {explanation && (
        <p className="whitespace-pre-wrap text-14 leading-relaxed text-theme-text [overflow-wrap:anywhere]">
          {explanation}
        </p>
      )}
      {isAudit && !isPending && !cancelled && !failed && !objective && (
        <p className="text-12 leading-relaxed text-theme-text-secondary">
          {t("chat.goal.auditRecorded")}
        </p>
      )}
      {failed && error && (
        <p
          role="alert"
          className="whitespace-pre-wrap text-14 text-theme-text [overflow-wrap:anywhere]"
        >
          {error}
        </p>
      )}
    </div>
  );
}

export const GoalItem = memo(function GoalItem(
  props: ToolDetailProps & {
    id?: string;
    toolName: "get_goal" | "update_goal";
  },
) {
  const { t } = useTranslation();
  const title = t(
    props.toolName === "get_goal"
      ? "chat.message.toolGetGoal"
      : "chat.message.toolUpdateGoal",
  );
  const parsed = parseSubagentControlResult(props.result);
  const status = props.isPending
    ? "loading"
    : props.cancelled
      ? "cancelled"
      : props.success === false || parsed?.status === "error"
        ? "error"
        : "idle";
  return (
    <CollapsiblePill
      status={status}
      icon={<Target size={12} className="shrink-0 opacity-50" />}
      label={title}
      animatedDots={props.isPending}
      variant="tool"
      expandable
      onPanelOpen={() =>
        openToolLivePanel({
          id: props.id,
          title,
          status,
          icon: <Target size={16} />,
          fallback: <GoalDetail {...props} />,
          buildDetail: (data) => (
            <GoalDetail {...toolDetailPropsFromPanelData(data)} />
          ),
          footer: (
            <ToolDurationFooter
              startedAt={props.startedAt}
              completedAt={props.completedAt}
            />
          ),
        })
      }
    />
  );
});
