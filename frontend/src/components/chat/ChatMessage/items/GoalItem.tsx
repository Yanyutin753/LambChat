import { memo } from "react";
import { Target } from "lucide-react";
import { useTranslation } from "react-i18next";
import { CollapsiblePill } from "../../../common";
import { ToolDurationFooter } from "./ToolDurationFooter";
import { ToolResultContent } from "./McpBlockPreview";
import { parseSubagentControlResult } from "../subagentPanelState";
import {
  openToolLivePanel,
  toolDetailPropsFromPanelData,
  type ToolDetailProps,
} from "./ToolLivePanelContent";

function GoalDetail({ args, result }: ToolDetailProps) {
  return (
    <div className="tool-panel-content min-w-0 space-y-3 overflow-y-auto p-3 sm:p-4">
      {Object.keys(args).length > 0 && <ToolResultContent result={args} />}
      {result !== undefined && <ToolResultContent result={result} />}
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
