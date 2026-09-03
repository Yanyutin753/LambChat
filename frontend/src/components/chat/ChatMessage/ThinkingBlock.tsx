import { useEffect, useMemo } from "react";
import { Brain } from "lucide-react";
import { useTranslation } from "react-i18next";
import { CollapsiblePill } from "../../common";
import type { CollapsibleStatus } from "../../common";
import {
  openPersistentToolPanel,
  updatePersistentToolPanel,
  isPersistentToolPanelOpen,
} from "./items/persistentToolPanelState";
import { SidebarMarkdownContent } from "./SidebarMarkdownContent";
import { buildStreamingThinkingPreview } from "./thinkingPreview";
import { useSmoothStreamText } from "./useSmoothStreamText";

export function ThinkingBlock({
  content,
  isStreaming,
  panelKey,
}: {
  content: string;
  isStreaming?: boolean;
  panelKey?: string;
}) {
  const { t } = useTranslation();

  const status: CollapsibleStatus = isStreaming ? "loading" : "success";

  // 思考文案平滑流出：片段到达后打字机式渐显，而非整块蹦出；历史回放全量
  const displayContent = useSmoothStreamText(content, !!isStreaming);

  useEffect(() => {
    if (!isPersistentToolPanelOpen(panelKey)) return;
    updatePersistentToolPanel(
      (prev) => ({
        ...prev,
        status,
        children: (
          <div className="p-3 sm:p-4 [&_.markdown-preview]:thinking-content">
            <SidebarMarkdownContent
              content={displayContent}
              isStreaming={isStreaming}
            />
          </div>
        ),
      }),
      panelKey,
    );
  }, [displayContent, isStreaming, panelKey, status]);

  // Show a brief preview of the reasoning content in the pill label
  const preview = useMemo(() => {
    if (!displayContent) return "";
    if (isStreaming) return buildStreamingThinkingPreview(displayContent);
    const text = displayContent.replace(/\n+/g, " ").trim();
    return text.length > 80 ? text.slice(0, 80) + "…" : text;
  }, [displayContent, isStreaming]);

  const label = isStreaming
    ? preview
      ? `${t("chat.message.thinking")} ${preview}`
      : t("chat.message.thinking")
    : preview || t("chat.message.thought");

  return (
    <CollapsiblePill
      status={status}
      icon={<Brain size={12} className="shrink-0 opacity-50" />}
      label={label}
      formatLabel={false}
      variant="thinking"
      animatedDots={isStreaming}
      expandable={!!content}
      onPanelOpen={() => {
        openPersistentToolPanel({
          title: t("chat.message.thought"),
          icon: <Brain size={16} />,
          status,
          panelKey,
          children: (
            <div className="p-3 sm:p-4 [&_.markdown-preview]:thinking-content">
              <SidebarMarkdownContent
                content={displayContent}
                isStreaming={isStreaming}
              />
            </div>
          ),
        });
      }}
    />
  );
}
