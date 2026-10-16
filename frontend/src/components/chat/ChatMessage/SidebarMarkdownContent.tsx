import { useState } from "react";
import { InteractiveIcon } from "../../common/InteractiveIcon";
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
    ? isStreaming
      ? content.slice(-SIDEBAR_MARKDOWN_PREVIEW_LIMIT)
      : content.slice(0, SIDEBAR_MARKDOWN_PREVIEW_LIMIT)
    : content;

  if (!shouldUsePreview) {
    return <MarkdownContent content={content} isStreaming={isStreaming} />;
  }

  return (
    <div className="sidebar-reasoning-preview flex h-full min-h-0 flex-col gap-2">
      <div className="relative min-h-0 flex-1 overflow-hidden rounded-md bg-theme-bg-card">
        <div
          tabIndex={0}
          aria-label={t("chat.message.thought")}
          className="sidebar-reasoning-preview__scroll h-full w-full overflow-auto whitespace-pre-wrap break-words px-3 pb-6 pt-2 text-[0.9375rem] leading-[1.75] text-theme-text-secondary sm:px-4"
        >
          {previewContent}
        </div>
        <div className="pointer-events-none absolute inset-x-0 bottom-0 h-10 bg-linear-to-t from-theme-bg-card to-transparent" />
      </div>
      {expandable && (
        <button
          type="button"
          onClick={() => setShowFull(true)}
          className="sidebar-reasoning-preview__expand inline-flex shrink-0 self-start min-h-8 items-center gap-1.5 rounded-md border border-theme-border bg-theme-bg-card px-2.5 text-12 font-medium text-theme-text-secondary transition-colors hover:bg-theme-bg-hover hover:text-theme-text"
        >
          <InteractiveIcon>
            <Maximize2 size={12} />
          </InteractiveIcon>
          {t("common.expand", "Expand")}
        </button>
      )}
    </div>
  );
}
