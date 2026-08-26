import { useMemo, useCallback, useEffect, useRef } from "react";
import type { TFunction } from "i18next";
import { ListTree } from "lucide-react";
import type { ListRange, VirtuosoHandle } from "react-virtuoso";
import type { Message } from "../../../types";
import {
  createMessageAnchorId,
  getOutlineActiveAnchorIdForRange,
  shouldShowMessageOutline,
  extractMessageOutline,
} from "./messageOutline";
import { MessageOutlinePanel } from "./MessageOutlinePanel";
import {
  closePersistentToolPanel,
  openPersistentToolPanel,
  isPersistentToolPanelOpen,
  updatePersistentToolPanel,
  type PersistentToolPanelState,
} from "../../chat/ChatMessage/items/persistentToolPanelState";

export interface ChatOutlineReturn {
  showOutline: boolean;
  outlineItems: ReturnType<typeof extractMessageOutline>;
  activeOutlineId: string | null;
  handleOpenOutline: () => void;
  handleVisibleRangeChange: (range: ListRange) => void;
}

export function useChatOutline(
  messages: Message[],
  virtuosoRef: React.RefObject<VirtuosoHandle | null>,
  assistantAvatar: string | null,
  outlineToggleRef: React.RefObject<(() => void) | null> | undefined,
  t: TFunction,
): ChatOutlineReturn {
  const showOutline = shouldShowMessageOutline(messages);
  const visibleRangeRef = useRef<ListRange | null>(null);
  const outlineItems = useMemo(
    () => (showOutline ? extractMessageOutline(messages) : []),
    [messages, showOutline],
  );

  const getActiveOutlineId = useCallback(() => {
    const rangeActiveId = getOutlineActiveAnchorIdForRange(
      messages,
      visibleRangeRef.current,
    );
    if (rangeActiveId) {
      return rangeActiveId;
    }

    const latestMessage = messages[messages.length - 1];
    return latestMessage ? createMessageAnchorId(latestMessage.id) : null;
  }, [messages]);

  const activeOutlineId = getActiveOutlineId();

  const handleOutlineNavigate = useCallback(
    (anchorId: string, messageIndex: number) => {
      // 瞬时跳转，与时间轴一致（smooth 在长虚拟列表上会缓慢爬行）
      virtuosoRef.current?.scrollToIndex({
        index: messageIndex,
        behavior: "auto",
        align: "start",
      });
      // After Virtuoso renders the message, scroll to the specific heading anchor
      requestAnimationFrame(() => {
        const el = document.getElementById(anchorId);
        if (el) {
          el.scrollIntoView({ behavior: "auto", block: "start" });
        }
      });
      requestAnimationFrame(() => {
        closePersistentToolPanel();
      });
    },
    [virtuosoRef],
  );

  const handleOpenOutline = useCallback(() => {
    if (isPersistentToolPanelOpen("outline")) {
      closePersistentToolPanel();
      return;
    }
    const isMobile = window.innerWidth < 640;
    openPersistentToolPanel({
      title: t("chat.outline"),
      icon: <ListTree size={18} strokeWidth={2} />,
      status: "idle",
      panelKey: "outline",
      viewMode: isMobile ? "center" : "sidebar",
      mobileFillViewport: isMobile,
      children: (
        <MessageOutlinePanel
          items={outlineItems}
          activeId={getActiveOutlineId()}
          onNavigate={handleOutlineNavigate}
          personaAvatar={assistantAvatar}
        />
      ),
    });
  }, [
    outlineItems,
    getActiveOutlineId,
    handleOutlineNavigate,
    t,
    assistantAvatar,
  ]);

  const handleVisibleRangeChange = useCallback(
    (range: ListRange) => {
      if (
        visibleRangeRef.current?.startIndex === range.startIndex &&
        visibleRangeRef.current?.endIndex === range.endIndex
      ) {
        return;
      }
      visibleRangeRef.current = range;

      if (!isPersistentToolPanelOpen("outline")) return;
      updatePersistentToolPanel(
        (prev: PersistentToolPanelState) => ({
          ...prev,
          children: (
            <MessageOutlinePanel
              items={outlineItems}
              activeId={getActiveOutlineId()}
              onNavigate={handleOutlineNavigate}
              personaAvatar={assistantAvatar}
            />
          ),
        }),
        "outline",
      );
    },
    [assistantAvatar, getActiveOutlineId, handleOutlineNavigate, outlineItems],
  );

  useEffect(() => {
    if (outlineToggleRef) {
      outlineToggleRef.current = showOutline ? handleOpenOutline : null;
    }
  }, [outlineToggleRef, showOutline, handleOpenOutline]);

  useEffect(() => {
    if (!isPersistentToolPanelOpen("outline")) return;
    updatePersistentToolPanel(
      (prev: PersistentToolPanelState) => ({
        ...prev,
        children: (
          <MessageOutlinePanel
            items={outlineItems}
            activeId={activeOutlineId}
            onNavigate={handleOutlineNavigate}
          />
        ),
      }),
      "outline",
    );
  }, [outlineItems, activeOutlineId, handleOutlineNavigate]);

  return {
    showOutline,
    outlineItems,
    activeOutlineId,
    handleOpenOutline,
    handleVisibleRangeChange,
  };
}
