import { useEffect, useState } from "react";
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
import { useSmoothStreamText } from "./useSmoothStreamText";
import { buildPanelSummary } from "./panelSummary";
import { stripActivityReferences } from "../../../utils/activityReferences";
import {
  formatElapsedCompact,
  formatElapsedHuman,
} from "./runStepsCollapseUtils";

export function ThinkingBlock({
  content: rawContent,
  isStreaming,
  terminalStatus,
  startedAt,
  completedAt,
  panelKey,
}: {
  content: string;
  isStreaming?: boolean;
  terminalStatus?: "error" | "cancelled";
  startedAt?: number;
  completedAt?: number;
  panelKey?: string;
}) {
  const content = stripActivityReferences(rawContent, !!isStreaming);
  const { t, i18n } = useTranslation();
  const [now, setNow] = useState(Date.now);
  useEffect(() => {
    if (!isStreaming || startedAt === undefined || completedAt !== undefined)
      return;
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, [isStreaming, startedAt, completedAt]);
  const end = completedAt ?? (isStreaming ? now : undefined);
  const formatElapsed = i18n.language?.toLowerCase().startsWith("zh")
    ? formatElapsedHuman
    : formatElapsedCompact;
  const duration =
    startedAt !== undefined &&
    end !== undefined &&
    Number.isFinite(startedAt) &&
    Number.isFinite(end) &&
    end - startedAt >= 1000
      ? formatElapsed(Math.floor((end - startedAt) / 1000))
      : "";

  const status: CollapsibleStatus = isStreaming
    ? "loading"
    : terminalStatus ?? "success";

  const settledLabel =
    terminalStatus === "error"
      ? t("chat.message.thinkingFailed")
      : terminalStatus === "cancelled"
        ? t("chat.message.thinkingCancelled")
        : t("chat.message.thought");

  const label = isStreaming ? t("chat.message.thinking") : settledLabel;
  const timedLabel = duration ? `${label} ${duration}` : label;

  // 思考文案平滑流出：片段到达后打字机式渐显，而非整块蹦出；历史回放全量
  const displayContent = useSmoothStreamText(content, !!isStreaming);
  const subtitle = buildPanelSummary(content);

  useEffect(() => {
    if (!isPersistentToolPanelOpen(panelKey)) return;
    updatePersistentToolPanel(
      (prev) => ({
        ...prev,
        status,
        title: timedLabel,
        subtitle,
        children: (
          <div className="right-panel-prose h-full min-h-0 [&_.markdown-preview]:thinking-content">
            <SidebarMarkdownContent
              content={displayContent}
              isStreaming={isStreaming}
            />
          </div>
        ),
      }),
      panelKey,
    );
  }, [displayContent, isStreaming, panelKey, status, subtitle, timedLabel]);

  return (
    <CollapsiblePill
      status={status}
      icon={<Brain size={12} className="shrink-0 opacity-50" />}
      label={timedLabel}
      description={displayContent}
      formatLabel={false}
      variant="thinking"
      animatedDots={isStreaming}
      expandable={!!content}
      onPanelOpen={() => {
        openPersistentToolPanel({
          title: timedLabel,
          subtitle,
          icon: <Brain size={16} />,
          status,
          panelKey,
          children: (
            <div className="right-panel-prose h-full min-h-0 [&_.markdown-preview]:thinking-content">
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
