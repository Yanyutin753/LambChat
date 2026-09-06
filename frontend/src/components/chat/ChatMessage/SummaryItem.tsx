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
  const suffix = useMemo(
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
        children: (
          <div className="p-3 sm:p-4">
            <MarkdownContent content={content} isStreaming={isStreaming} />
          </div>
        ),
      }),
      panelKey,
    );
  }, [content, isStreaming, panelKey, status]);

  return (
    <CollapsiblePill
      status={status}
      icon={<FileText size={12} className="shrink-0 opacity-50" />}
      label={t("chat.message.summary")}
      suffix={
        <span className="text-xs font-mono font-medium min-w-0 truncate overflow-hidden leading-none">
          {suffix}
        </span>
      }
      variant="summary"
      expandable={!!content}
      onPanelOpen={() => {
        openPersistentToolPanel({
          title: t("chat.message.summary"),
          icon: <FileText size={16} />,
          status,
          panelKey,
          children: (
            <div className="p-3 sm:p-4">
              <MarkdownContent content={content} isStreaming={isStreaming} />
            </div>
          ),
        });
      }}
    />
  );
}
