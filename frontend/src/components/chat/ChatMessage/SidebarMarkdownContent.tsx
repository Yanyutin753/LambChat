import { useRef, useState } from "react";
import { InteractiveIcon } from "../../common/InteractiveIcon";
import { ArrowDown, Maximize2 } from "lucide-react";
import { useTranslation } from "react-i18next";
import { usePanelScrollFollow } from "./usePanelScrollFollow";
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
  const openedWhileStreaming = useRef(!!isStreaming);
  const [showFull, setShowFull] = useState(false);
  const { scrollRef, contentRef, showScrollToBottom, jumpToBottom } =
    usePanelScrollFollow(content, !!isStreaming);
  const shouldUsePreview =
    (isStreaming ||
      openedWhileStreaming.current ||
      content.length > SIDEBAR_MARKDOWN_PREVIEW_LIMIT) &&
    !showFull;
  // Keep streamed text stable while reading; trimming its head moves the viewport.
  const previewContent = shouldUsePreview
    ? isStreaming || openedWhileStreaming.current
      ? content
      : content.slice(0, SIDEBAR_MARKDOWN_PREVIEW_LIMIT)
    : content;

  return (
    <div className="sidebar-reasoning-preview relative flex h-full min-h-0 flex-col gap-2">
      <div className="relative min-h-0 flex-1 overflow-hidden rounded-md bg-theme-bg-card">
        <div
          ref={scrollRef}
          tabIndex={0}
          aria-label={t("chat.message.thought")}
          className="sidebar-reasoning-preview__scroll h-full w-full overflow-auto whitespace-pre-wrap break-words px-3 pb-6 pt-2 text-[0.9375rem] leading-[1.75] text-theme-text-secondary sm:px-4"
        >
          <div
            ref={contentRef}
            className={shouldUsePreview ? undefined : "whitespace-normal"}
          >
            {shouldUsePreview ? (
              previewContent
            ) : (
              <MarkdownContent content={content} isStreaming={isStreaming} />
            )}
          </div>
        </div>
        <div className="pointer-events-none absolute inset-x-0 bottom-0 h-10 bg-linear-to-t from-theme-bg-card to-transparent" />
      </div>
      {showScrollToBottom && (
        <button
          type="button"
          onClick={jumpToBottom}
          aria-label={t("common.scrollToBottom")}
          className="absolute bottom-12 left-1/2 z-10 inline-flex min-h-9 w-max max-w-[calc(100%-1.5rem)] -translate-x-1/2 items-center gap-1.5 rounded-full border border-theme-border bg-theme-bg-card/95 px-3 text-12 font-medium text-theme-text-secondary shadow-lg transition-colors hover:bg-theme-bg-hover hover:text-theme-text"
        >
          <InteractiveIcon>
            <ArrowDown size={13} />
          </InteractiveIcon>
          {t("common.scrollToBottom")}
        </button>
      )}
      {expandable && shouldUsePreview && (
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
