import { useEffect, useMemo } from "react";
import { FileText } from "lucide-react";
import { useTranslation } from "react-i18next";
import { CollapsiblePill } from "../../common";
import type { CollapsibleStatus } from "../../common/CollapsiblePill";
import {
  openPersistentToolPanel,
  updatePersistentToolPanel,
  isPersistentToolPanelOpen,
} from "./items/persistentToolPanelState";
import { MarkdownContent } from "./MarkdownContent";
import { buildPanelSummary } from "./panelSummary";
import { stripActivityReferences } from "../../../utils/activityReferences";

export function SummaryItem({
  content,
  isStreaming,
  panelKey,
  freedTokens,
}: {
  content: string;
  isStreaming?: boolean;
  panelKey?: string;
  freedTokens?: number;
}) {
  const { t } = useTranslation();

  const status: CollapsibleStatus = isStreaming ? "loading" : "success";
  const visibleContent = stripActivityReferences(content, isStreaming);
  const subtitle = buildPanelSummary(visibleContent);
  const description = useMemo(
    () =>
      freedTokens != null
        ? t("chat.message.summaryFreedTokens", {
            tokens: freedTokens.toLocaleString(),
          })
        : t("chat.message.summaryDescription"),
    [t, freedTokens],
  );

  useEffect(() => {
    if (!isPersistentToolPanelOpen(panelKey)) return;
    updatePersistentToolPanel(
      (prev) => ({
        ...prev,
        status,
        subtitle,
        children: (
          <div className="p-3 sm:p-4">
            <MarkdownContent
              content={visibleContent}
              isStreaming={isStreaming}
            />
          </div>
        ),
      }),
      panelKey,
    );
  }, [visibleContent, isStreaming, panelKey, status, subtitle]);

  return (
    <CollapsiblePill
      status={status}
      icon={<FileText size={12} className="shrink-0 opacity-50" />}
      label={t("chat.message.summary")}
      description={description}
      variant="summary"
      expandable={!!visibleContent}
      onPanelOpen={() => {
        openPersistentToolPanel({
          title: t("chat.message.summary"),
          subtitle,
          icon: <FileText size={16} />,
          status,
          panelKey,
          children: (
            <div className="p-3 sm:p-4">
              <MarkdownContent
                content={visibleContent}
                isStreaming={isStreaming}
              />
            </div>
          ),
        });
      }}
    />
  );
}
