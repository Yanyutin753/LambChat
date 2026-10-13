import { memo } from "react";
import { Workflow } from "lucide-react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { CollapsiblePill } from "../../../common";
import { parseSubagentControlResult } from "../subagentPanelState";
import { ToolDurationFooter } from "./ToolDurationFooter";
import { ToolResultContent } from "./McpBlockPreview";
import { openToolLivePanel, toolDetailPropsFromPanelData, type ToolDetailProps } from "./ToolLivePanelContent";

function BackgroundConversationLink(props: ToolDetailProps) {
  const { t } = useTranslation();
  const result = parseSubagentControlResult(props.result);
  if (props.isPending || props.cancelled || props.success === false ||
    (result?.status !== "queued" && result?.status !== "running") ||
    typeof result.session_id !== "string" || !result.session_id.trim()) return null;
  return <Link to={`/chat/${encodeURIComponent(result.session_id)}`}
    className="inline-flex min-h-9 max-w-full items-center rounded px-1 text-12 text-theme-primary underline underline-offset-4 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-theme-primary">
    {t("chat.message.toolBackgroundTaskOpen")}
  </Link>;
}

function BackgroundTaskDetail(props: ToolDetailProps) {
  const result = parseSubagentControlResult(props.result);
  return <div className="min-w-0 space-y-3 overflow-y-auto p-3 sm:p-4">
    {typeof props.args.description === "string" && <ToolResultContent result={props.args.description} hideCopyButton />}
    <BackgroundConversationLink {...props} />
    {(props.success === false || result?.status === "error") && props.result && <ToolResultContent result={props.result} hideCopyButton />}
  </div>;
}

export const StartBackgroundTaskItem = memo(function StartBackgroundTaskItem(props: ToolDetailProps & { id?: string }) {
  const { t } = useTranslation();
  const result = parseSubagentControlResult(props.result);
  const failed = props.success === false || result?.status === "error";
  const accepted = !props.isPending && !props.cancelled && !failed &&
    (result?.status === "queued" || result?.status === "running");
  const title = t("chat.message.toolStartBackgroundTask");
  const status = props.isPending ? "loading" : props.cancelled ? "cancelled" : failed ? "error" : "idle";
  const label = [title, props.cancelled ? t("chat.cancelled") : failed
    ? t("chat.message.toolBackgroundTaskUnavailable") : accepted
      ? t("chat.message.toolBackgroundTaskSubmitted") : ""].filter(Boolean).join(" · ");
  return <div className="flex min-w-0 max-w-full flex-wrap items-center gap-x-2">
    <CollapsiblePill status={status} icon={<Workflow size={12} className="shrink-0 opacity-50" />}
      label={label} animatedDots={props.isPending} variant="tool" formatLabel={false} expandable
      onPanelOpen={() => openToolLivePanel({ id: props.id, title, status, icon: <Workflow size={16} />,
        fallback: <BackgroundTaskDetail {...props} />,
        buildDetail: (data) => <BackgroundTaskDetail {...toolDetailPropsFromPanelData(data)} />,
        footer: <ToolDurationFooter startedAt={props.startedAt} completedAt={props.completedAt} />,
      })} />
    <BackgroundConversationLink {...props} />
  </div>;
});
