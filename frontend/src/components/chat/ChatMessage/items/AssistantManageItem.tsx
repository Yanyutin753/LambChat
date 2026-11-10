import { useEffect } from "react";
import { Link } from "react-router-dom";
import { Users } from "lucide-react";
import { useTranslation } from "react-i18next";
import { CollapsiblePill } from "../../../common";
import { parseSubagentControlResult } from "../subagentPanelState";
import { AssistantToolResult } from "./AssistantToolResult";
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
  const assistants =
    status === "idle" && Array.isArray(result?.assistants)
      ? result.assistants
      : undefined;
  const description = assistants
    ?.slice(0, 3)
    .map((item: unknown) =>
      item &&
      typeof item === "object" &&
      "name" in item &&
      typeof item.name === "string"
        ? item.name
        : "",
    )
    .filter(Boolean)
    .join(" ");
  return (
    <div className="flex min-w-0 flex-wrap items-center gap-2">
      <CollapsiblePill
        status={status}
        variant="tool"
        icon={<Users size={12} className="opacity-50" />}
        label={[
          title,
          assistants &&
            t("chat.message.toolAssistantCount", { count: assistants.length }),
          description,
        ]
          .filter(Boolean)
          .join(" ")}
        animatedDots={props.isPending}
        expandable
        onPanelOpen={() =>
          openToolLivePanel({
            id: props.id,
            title,
            status,
            icon: <Users size={16} />,
            fallback: (
              <div className="tool-panel-content min-w-0 p-3">
                <AssistantToolResult result={props.result} />
              </div>
            ),
            buildDetail: (data) => (
              <div className="tool-panel-content min-w-0 p-3">
                <AssistantToolResult
                  result={toolDetailPropsFromPanelData(data).result}
                />
              </div>
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
