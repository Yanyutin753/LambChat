import { InteractiveIcon } from "../../common/InteractiveIcon";
import {
  useCallback,
  useContext,
  useSyncExternalStore,
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { RightPanelActiveContext } from "../../common/useRightPanelEntry";
import { ArrowDown } from "lucide-react";
import { useTranslation } from "react-i18next";
import { ChatMessage } from "./index";
import { buildSubagentConversation } from "./subagentPanelState";
import {
  subagentPanelStore,
  type SubagentPanelData,
} from "./subagentPanelStore";
import {
  isNearSubagentPanelBottom,
  startSubagentPanelScrollToBottom,
  shouldAutoScrollSubagentPanel,
} from "./subagentPanelScroll";
function useSubagentPanelData(
  agentId: string,
  active: boolean,
): SubagentPanelData | undefined {
  const subscribe = useCallback(
    (listener: () => void) =>
      active ? subagentPanelStore.subscribe(agentId, listener) : () => {},
    [active, agentId],
  );
  return useSyncExternalStore(subscribe, () => subagentPanelStore.get(agentId));
}

export function SubagentPanelContent({ agentId }: { agentId: string }) {
  const { t } = useTranslation();
  const active = useContext(RightPanelActiveContext);
  const data = useSubagentPanelData(agentId, active);
  const scrollRef = useRef<HTMLDivElement>(null);
  const contentRef = useRef<HTMLDivElement>(null);
  const bottomRef = useRef<HTMLDivElement>(null);
  const userScrolledUpRef = useRef(false);
  const programmaticScrollRef = useRef(false);
  const stopAutoScrollRef = useRef<(() => void) | null>(null);
  const [showScrollToBottom, setShowScrollToBottom] = useState(false);
  const messages = useMemo(
    () => (data ? buildSubagentConversation(data) : []),
    [data],
  );

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
    if (!active) stopAutoScroll();
    return () => stopAutoScroll();
  }, [active, stopAutoScroll]);

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
    if (!active) return;
    if (
      !shouldAutoScrollSubagentPanel({
        scroller: scrollRef.current,
        userScrolledUp: userScrolledUpRef.current,
      })
    ) {
      return;
    }

    scrollToBottom();
  }, [active, data, scrollToBottom]);

  useEffect(() => {
    const scroller = scrollRef.current;
    if (!active || !scroller || typeof ResizeObserver === "undefined") {
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
  }, [active, startAutoScroll]);

  // 面板历史返回时快照会恢复滚动位置（含 lazy 内容，~600ms 窗口）。
  // 窗口结束后固化滚动意图：恢复到非底部 → 视为用户已上滑，后续流式
  // 更新不再把面板拉回底部；在底部则维持跟随。
  useEffect(() => {
    const timer = window.setTimeout(() => {
      const scroller = scrollRef.current;
      if (scroller && !isNearSubagentPanelBottom(scroller)) {
        userScrolledUpRef.current = true;
        setShowScrollToBottom(true);
      }
    }, 650);
    return () => window.clearTimeout(timer);
  }, []);

  if (!data) return null;
  return (
    <div className="relative flex h-full min-h-0 flex-col font-sans">
      <div
        ref={scrollRef}
        onScroll={handleScroll}
        className="min-h-0 flex-1 overflow-y-auto py-4"
      >
        <div ref={contentRef} className="space-y-6">
          {messages.map((message, index) => (
            <ChatMessage
              key={message.id}
              message={message}
              personaName={data.agentName}
              personaAvatar={data.agentAvatar}
              isFirst={index === 0}
              isLastMessage={index === messages.length - 1}
              showFeedbackAndShareActions={false}
            />
          ))}
          <div ref={bottomRef} className="h-px" />
        </div>
      </div>
      {showScrollToBottom && (
        <button
          type="button"
          onClick={handleJumpToBottom}
          aria-label={t("common.scrollToBottom")}
          className="absolute bottom-3 left-1/2 z-10 inline-flex min-h-9 w-max max-w-[calc(100%-1.5rem)] -translate-x-1/2 items-center gap-1.5 rounded-full border border-theme-border bg-theme-bg-card/95 px-3 text-12 font-medium text-theme-text-secondary shadow-lg transition-colors hover:bg-theme-bg-hover hover:text-theme-text"
        >
          <InteractiveIcon>
            <ArrowDown size={13} />
          </InteractiveIcon>
          {t("common.scrollToBottom")}
        </button>
      )}
    </div>
  );
}
