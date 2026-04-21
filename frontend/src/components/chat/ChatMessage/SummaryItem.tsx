import { useEffect } from "react";
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
}: {
  content: string;
  isStreaming?: boolean;
  panelKey?: string;
}) {
  const { t } = useTranslation();

  const status: CollapsibleStatus = isStreaming ? "loading" : "success";

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
