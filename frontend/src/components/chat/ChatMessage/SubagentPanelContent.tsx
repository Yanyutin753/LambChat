import {
  useCallback,
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { ArrowDown, Maximize2 } from "lucide-react";
import { useTranslation } from "react-i18next";
import { LoadingSpinner, CopyButton } from "../../common";
import type { MessagePart } from "../../../types";
import { MessagePartRenderer } from "./MessagePartRenderer";
import { createSubagentAnchorOwnerId } from "./messagePartAnchors";
import {
  subagentPanelStore,
  type SubagentPanelData,
} from "./subagentPanelStore";
import {
  isNearSubagentPanelBottom,
  startSubagentPanelScrollToBottom,
  shouldAutoScrollSubagentPanel,
} from "./subagentPanelScroll";
import { shouldExpandSubagentProcessByDefault } from "./subagentPanelControl";
import { CollapsibleSection } from "./CollapsibleSection";
import {
  SidebarMarkdownContent,
  SUBAGENT_PARTS_PREVIEW_LIMIT,
} from "./SidebarMarkdownContent";

function useSubagentPanelData(agentId: string): SubagentPanelData | undefined {
  const [, forceRender] = useState(0);

  useEffect(() => {
    const listener = () => forceRender((n) => n + 1);
    return subagentPanelStore.subscribe(agentId, listener);
  }, [agentId]);

  return subagentPanelStore.get(agentId);
}

function extractPartsText(parts: MessagePart[]): string {
  return parts
    .map((p) => {
      if (p.type === "text" || p.type === "thinking") return p.content;
      if (p.type === "tool")
        return `[${p.name}]${p.result != null ? " " + String(p.result) : ""}`;
      if (p.type === "subagent")
        return `[${p.agent_name}]${p.result ? " " + p.result : ""}`;
      return "";
    })
    .filter(Boolean)
    .join("\n\n");
}

export function SubagentPanelContent({ agentId }: { agentId: string }) {
  const { t } = useTranslation();
  const data = useSubagentPanelData(agentId);
  const scrollRef = useRef<HTMLDivElement>(null);
  const contentRef = useRef<HTMLDivElement>(null);
  const bottomRef = useRef<HTMLDivElement>(null);
  const userScrolledUpRef = useRef(false);
  const programmaticScrollRef = useRef(false);
  const stopAutoScrollRef = useRef<(() => void) | null>(null);
  const [showScrollToBottom, setShowScrollToBottom] = useState(false);

  const markProgrammaticScroll = useCallback(() => {
    programmaticScrollRef.current = true;
    window.setTimeout(() => {
      programmaticScrollRef.current = false;
    }, 0);
  }, []);

  const stopAutoScroll = useCallback(() => {
    stopAutoScrollRef.current?.();
    stopAutoScrollRef.current = null;
  }, []);

  const startAutoScroll = useCallback(() => {
    stopAutoScroll();
    stopAutoScrollRef.current = startSubagentPanelScrollToBottom({
      scroller: scrollRef.current,
      footer: bottomRef.current,
      shouldAbort: () => userScrolledUpRef.current,
      onAutoScroll: markProgrammaticScroll,
    });
  }, [markProgrammaticScroll, stopAutoScroll]);

  useEffect(() => {
    return () => stopAutoScroll();
  }, [stopAutoScroll]);

  const scrollToBottom = useCallback(() => {
    startAutoScroll();
  }, [startAutoScroll]);

  const handleJumpToBottom = useCallback(() => {
    userScrolledUpRef.current = false;
    setShowScrollToBottom(false);
    startAutoScroll();
  }, [startAutoScroll]);

  const handleScroll = useCallback(() => {
    const scroller = scrollRef.current;
    if (!scroller || programmaticScrollRef.current) return;
    userScrolledUpRef.current = !isNearSubagentPanelBottom(scroller);
    setShowScrollToBottom(userScrolledUpRef.current);
    if (userScrolledUpRef.current) {
      stopAutoScroll();
    }
  }, [stopAutoScroll]);

  useLayoutEffect(() => {
    if (
      !shouldAutoScrollSubagentPanel({
        scroller: scrollRef.current,
        userScrolledUp: userScrolledUpRef.current,
      })
    ) {
      return;
    }

    scrollToBottom();
  }, [data, scrollToBottom]);

  useEffect(() => {
    const scroller = scrollRef.current;
    if (!scroller || typeof ResizeObserver === "undefined") {
      return;
    }

    const observer = new ResizeObserver(() => {
      if (
        shouldAutoScrollSubagentPanel({
          scroller,
          userScrolledUp: userScrolledUpRef.current,
        })
      ) {
        startAutoScroll();
      }
    });

    observer.observe(scroller);
    if (contentRef.current) {
      observer.observe(contentRef.current);
    }

    return () => observer.disconnect();
  }, [startAutoScroll]);

  const partsText = useMemo(
    () => (data?.parts?.length ? extractPartsText(data.parts) : ""),
    [data?.parts],
  );
  const [showFullProcess, setShowFullProcess] = useState(false);
  if (!data) return null;

  const effectiveStatus =
    data.status ||
    (data.isPending ? "running" : data.success ? "complete" : "error");
  const shouldUsePartsPreview =
    !!data.parts?.length &&
    !showFullProcess &&
    (data.isPending || partsText.length > SUBAGENT_PARTS_PREVIEW_LIMIT);

  return (
    <div
      ref={scrollRef}
      onScroll={handleScroll}
      className="relative flex h-full min-h-0 flex-col overflow-y-auto p-2 sm:p-4"
    >
      <div ref={contentRef} className="flex min-h-0 flex-1 flex-col space-y-3">
        {data.input && (
          <CollapsibleSection
            title={t("chat.message.args")}
            action={<CopyButton text={data.input} />}
          >
            <div className="text-sm text-stone-600 dark:text-stone-300 leading-relaxed">
              <SidebarMarkdownContent content={data.input} />
            </div>
          </CollapsibleSection>
        )}
        {data.parts && data.parts.length > 0 && (
          <CollapsibleSection
            title={t("chat.message.processing")}
            defaultExpanded={shouldExpandSubagentProcessByDefault(
              effectiveStatus,
            )}
            action={<CopyButton text={partsText} />}
          >
            {shouldUsePartsPreview ? (
              <div className="space-y-2">
                <SidebarMarkdownContent
                  content={partsText}
                  isStreaming={data.isPending}
                  expandable={false}
                />
                <button
                  type="button"
                  onClick={() => setShowFullProcess(true)}
                  className="inline-flex min-h-8 items-center gap-1.5 rounded-md border border-theme-border bg-theme-bg-card px-2.5 text-xs font-medium text-theme-text-secondary transition-colors hover:bg-theme-bg-subtle hover:text-theme-text"
                >
                  <Maximize2 size={12} />
                  {t("common.expand", "Expand")}
                </button>
              </div>
            ) : (
              <div className="space-y-2">
                {data.parts.map((part, index) => (
                  <MessagePartRenderer
                    key={index}
                    part={part}
                    messageId={createSubagentAnchorOwnerId(agentId)}
                    partIndex={index}
                    isStreaming={data.isPending}
                    isLast={index === data.parts!.length - 1}
                  />
                ))}
              </div>
            )}
          </CollapsibleSection>
        )}
        {data.error && effectiveStatus === "error" && (
          <CollapsibleSection
            title={t("chat.message.error")}
            action={<CopyButton text={data.error} />}
            variant="error"
          >
            <div className="text-xs text-red-700 dark:text-red-300 leading-relaxed">
              {data.error}
            </div>
          </CollapsibleSection>
        )}
        {data.result && effectiveStatus === "complete" && (
          <CollapsibleSection
            title={t("chat.message.result")}
            action={<CopyButton text={data.result} />}
            expandedClassName="flex min-h-0 flex-col grow shrink-0"
          >
            <div className="text-sm text-stone-700 dark:text-stone-300 leading-relaxed">
              <SidebarMarkdownContent content={data.result} />
            </div>
          </CollapsibleSection>
        )}
        {data.isPending && !data.parts?.length && (
          <div className="flex items-center gap-2 text-stone-500 dark:text-stone-400">
            <LoadingSpinner size="sm" />
            <span className="text-sm">{t("chat.message.executing")}</span>
          </div>
        )}
        <div ref={bottomRef} className="h-px" />
      </div>
      {showScrollToBottom && (
        <button
          type="button"
          onClick={handleJumpToBottom}
          className="sticky bottom-3 left-1/2 z-10 mt-3 inline-flex min-h-9 -translate-x-1/2 items-center gap-1.5 rounded-full border border-theme-border bg-theme-bg-card/95 px-3 text-xs font-medium text-theme-text-secondary shadow-lg transition-colors hover:bg-theme-bg-subtle hover:text-theme-text"
        >
          <ArrowDown size={13} />
          {t("common.scrollToBottom")}
        </button>
      )}
    </div>
  );
}
