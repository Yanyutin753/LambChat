import { useEffect } from "react";
import { Link } from "react-router-dom";
import { Users } from "lucide-react";
import { useTranslation } from "react-i18next";
import { CollapsiblePill } from "../../../common";
import { parseSubagentControlResult } from "../subagentPanelState";
import { ToolResultContent } from "./McpBlockPreview";
import {
  openToolLivePanel,
  toolDetailPropsFromPanelData,
  type ToolDetailProps,
} from "./ToolLivePanelContent";
export function AssistantManageItem(
  props: ToolDetailProps & { id?: string; toolName: string },
) {
  const { t } = useTranslation();
  const result = parseSubagentControlResult(props.result);
  const saved =
    !props.isPending &&
    !props.cancelled &&
    props.success !== false &&
    result?.success === true &&
    typeof result.id === "string";
  useEffect(() => {
    if (saved) window.dispatchEvent(new Event("assistants:changed"));
  }, [saved, result?.id]);
  const title = t(`assistants.tools.${props.toolName}`);
  const status = props.isPending
    ? "loading"
    : props.cancelled
      ? "cancelled"
      : props.success === false || result?.error
        ? "error"
        : "idle";
  return (
    <div className="flex min-w-0 flex-wrap items-center gap-2">
      <CollapsiblePill
        status={status}
        variant="tool"
        icon={<Users size={12} className="opacity-50" />}
        label={title}
        animatedDots={props.isPending}
        expandable
        onPanelOpen={() =>
          openToolLivePanel({
            id: props.id,
            title,
            status,
            icon: <Users size={16} />,
            fallback: <ToolResultContent result={props.result} />,
            buildDetail: (data) => (
              <ToolResultContent
                result={toolDetailPropsFromPanelData(data).result}
              />
            ),
          })
        }
      />
      {saved && (
        <Link
          className="truncate text-13 text-theme-primary underline underline-offset-4"
          to={`/assistants/${encodeURIComponent(result.id as string)}`}
        >
          {typeof result.name === "string"
            ? result.name
            : t("assistants.openConversation")}
        </Link>
      )}
    </div>
  );
}
