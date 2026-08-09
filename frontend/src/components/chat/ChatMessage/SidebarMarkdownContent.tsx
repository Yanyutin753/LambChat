import { useState } from "react";
import { Maximize2 } from "lucide-react";
import { useTranslation } from "react-i18next";
import { MarkdownContent } from "./MarkdownContent";

export const SIDEBAR_MARKDOWN_PREVIEW_LIMIT = 12_000;
export const SUBAGENT_PARTS_PREVIEW_LIMIT = 20_000;

export function SidebarMarkdownContent({
  content,
  isStreaming,
  expandable = true,
}: {
  content: string;
  isStreaming?: boolean;
  expandable?: boolean;
}) {
  const { t } = useTranslation();
  const [showFull, setShowFull] = useState(false);
  const shouldUsePreview =
    (isStreaming || content.length > SIDEBAR_MARKDOWN_PREVIEW_LIMIT) &&
    !showFull;
  const previewContent = shouldUsePreview
    ? content.slice(-SIDEBAR_MARKDOWN_PREVIEW_LIMIT)
    : content;

  if (!shouldUsePreview) {
    return <MarkdownContent content={content} isStreaming={isStreaming} />;
  }

  return (
    <div className="space-y-2">
      <div className="relative overflow-hidden rounded-md bg-theme-bg-card">
        <div className="max-h-[min(58vh,680px)] w-full overflow-auto whitespace-pre-wrap break-words px-3 pb-6 pt-2 text-[0.9375rem] leading-[1.75] text-theme-text-secondary sm:px-4">
          {previewContent}
        </div>
        <div className="pointer-events-none absolute inset-x-0 bottom-0 h-10 bg-gradient-to-t from-theme-bg-card to-transparent" />
      </div>
      {expandable && (
        <button
          type="button"
          onClick={() => setShowFull(true)}
          className="inline-flex min-h-8 items-center gap-1.5 rounded-md border border-theme-border bg-theme-bg-card px-2.5 text-xs font-medium text-theme-text-secondary transition-colors hover:bg-theme-bg-subtle hover:text-theme-text"
        >
          <Maximize2 size={12} />
          {t("common.expand", "Expand")}
        </button>
      )}
    </div>
  );
}
