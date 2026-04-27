import { useRef, useEffect, useState, useCallback } from "react";
import type { VirtuosoHandle } from "react-virtuoso";
import type { Message } from "../../../types";
import type { ExternalNavigationTargetFile } from "./externalNavigationState";
import {
  forceScrollerToPhysicalBottom,
  getAutoScrollResumeThresholdPx,
  getAwayFromBottomThresholdPx,
  shouldAutoScrollAfterViewportChange,
  startVirtuosoScrollToBottom,
} from "./messageScrollUtils";
import { createMessageAnchorId } from "./messageOutline";
import {
  createExternalNavigationElementResolver,
  ensureSubagentPanelsOpen,
  findExternalNavigationMatchForRunId,
  findMessageIndexForExternalNavigation,
  findMessageIndexForRunId,
  findRevealPartMatchInMessage,
  focusElementForExternalNavigation,
  highlightElementForExternalNavigation,
  scrollElementIntoViewWithRetries,
  shouldDeferExternalNavigationScroll,
  shouldKeepExternalNavigationPending,
  shouldScrollExternalNavigationFallbackToMessage,
} from "./useMessageScroll.externalNavigation";
import {
  createMessageScrollFollowState,
  getMessageScrollSessionResetState,
  getMessageUpdateScrollAction,
  shouldResetMessageScrollStateForSessionChange,
  getNextMessageScrollFollowStateForAtBottomChange,
  getNextMessageScrollFollowStateForBottomScroll,
  getNextMessageScrollFollowStateForUserGesture,
  getNextMessageScrollFollowStateForUserIntent,
  getNextMessageScrollFollowStateForUserScroll,
  shouldArmPendingHistoryScroll,
  shouldFinalizeHistoryLoadScroll,
} from "./useMessageScroll.followState";

interface UseMessageScrollReturn {
  messagesContainerRef: React.RefObject<HTMLDivElement | null>;
  virtuosoRef: React.RefObject<VirtuosoHandle | null>;
  virtuosoScrollerRef: React.RefObject<HTMLDivElement | null>;
  messagesEndRef: React.RefObject<HTMLDivElement | null>;
  isNearBottom: boolean;
  showScrollTop: boolean;
  handleVirtuosoAtBottomChange: (atBottom: boolean) => void;
  scrollToBottom: () => void;
  scrollToTop: () => void;
}

type AutoScrollMode = "default" | "history-finalize";

export function useMessageScroll(
  messages: Pick<Message, "id" | "role" | "isStreaming" | "parts" | "runId">[],
  sessionId?: string | null,
  externalNavigationToken?: string | null,
  externalNavigationTargetFile?: ExternalNavigationTargetFile | null,
  externalNavigationTargetRunId?: string | null,
  externalNavigationTargetRunPending = false,
  externalScrollToBottom = false,
  isLoadingHistory = false,
): UseMessageScrollReturn {
  const MOBILE_BOTTOM_BREATHING_ROOM_PX = 96;
  const DESKTOP_BOTTOM_BREATHING_ROOM_PX = 16;
  const isMobileViewport =
    typeof window !== "undefined" ? window.innerWidth < 640 : false;
  const bottomBreathingRoomPx = isMobileViewport
    ? MOBILE_BOTTOM_BREATHING_ROOM_PX
    : DESKTOP_BOTTOM_BREATHING_ROOM_PX;
  const awayFromBottomThresholdPx = getAwayFromBottomThresholdPx(
    isMobileViewport,
    bottomBreathingRoomPx,
  );
  const autoScrollResumeThresholdPx = getAutoScrollResumeThresholdPx(
    isMobileViewport,
    bottomBreathingRoomPx,
  );
  const messagesContainerRef = useRef<HTMLDivElement>(null);
  const virtuosoRef = useRef<VirtuosoHandle>(null);
  const virtuosoScrollerRef = useRef<HTMLDivElement>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const [isNearBottom, setIsNearBottom] = useState(true);
  const [showScrollTop, setShowScrollTop] = useState(false);
  const rafRef = useRef<number>(0);
  const viewportResizeRafRef = useRef<number>(0);
  const scrollCleanupRef = useRef<(() => void) | null>(null);
  const anchorScrollCleanupRef = useRef<(() => void) | null>(null);
  const highlightCleanupRef = useRef<(() => void) | null>(null);
  const pendingExternalNavigationRef = useRef<{
    token: string;
    targetFile: ExternalNavigationTargetFile | null;
    scrollToBottom: boolean;
  } | null>(null);
  const previousSessionIdRef = useRef(sessionId);
  const previousMessagesRef = useRef(messages);
  const isNearBottomRef = useRef(true);

  const userScrolledUpRef = useRef(false);
  const autoScrollActiveRef = useRef(false);
  const ignoreProgrammaticScrollUntilRef = useRef(0);
  const streamLockActiveRef = useRef(false);
  const manualDetachFromStreamRef = useRef(false);
  const streamingAssistantActiveRef = useRef(false);
  const pendingHistoryScrollRef = useRef(false);
  const historyLoadActiveRef = useRef(isLoadingHistory);
  const historyScrollArmedRef = useRef(false);
  const isLoadingHistoryRef = useRef(isLoadingHistory);

  const latestMessage = messages[messages.length - 1];
  const hasStreamingAssistantMessage =
    latestMessage?.role === "assistant" && latestMessage.isStreaming === true;

  useEffect(() => {
    streamingAssistantActiveRef.current = hasStreamingAssistantMessage;
  }, [hasStreamingAssistantMessage]);

  useEffect(() => {
    isLoadingHistoryRef.current = isLoadingHistory;
  }, [isLoadingHistory]);

  useEffect(() => {
    const previousSessionId = previousSessionIdRef.current;
    if (previousSessionId === sessionId) {
      return;
    }

    previousSessionIdRef.current = sessionId;
    if (
      !shouldResetMessageScrollStateForSessionChange({
        previousSessionId,
        sessionId,
        messageCount: messages.length,
      })
    ) {
      return;
    }

    const resetState = getMessageScrollSessionResetState();

    cancelAnimationFrame(rafRef.current);
    cancelAnimationFrame(viewportResizeRafRef.current);
    scrollCleanupRef.current?.();
    scrollCleanupRef.current = null;

    userScrolledUpRef.current = resetState.userScrolledUp;
    autoScrollActiveRef.current = resetState.autoScrollActive;
    streamLockActiveRef.current = resetState.streamLockActive;
    manualDetachFromStreamRef.current = resetState.manualDetachFromStream;
    pendingHistoryScrollRef.current = resetState.pendingHistoryScroll;
    historyScrollArmedRef.current = resetState.historyScrollArmed;
    ignoreProgrammaticScrollUntilRef.current = 0;
    isNearBottomRef.current = resetState.isNearBottom;
    previousMessagesRef.current = messages;
    historyLoadActiveRef.current = isLoadingHistory;

    setIsNearBottom(resetState.isNearBottom);
    setShowScrollTop(resetState.showScrollTop);
  }, [isLoadingHistory, messages, sessionId]);

  const handleVirtuosoAtBottomChange = useCallback((atBottom: boolean) => {
    cancelAnimationFrame(rafRef.current);
    rafRef.current = requestAnimationFrame(() => {
      setIsNearBottom(atBottom);
      isNearBottomRef.current = atBottom;
      if (atBottom) {
        const nextFollowState =
          getNextMessageScrollFollowStateForAtBottomChange({
            state: createMessageScrollFollowState({
              userScrolledUp: userScrolledUpRef.current,
              autoScrollActive: autoScrollActiveRef.current,
              streamLockActive: streamLockActiveRef.current,
              manualDetachFromStream: manualDetachFromStreamRef.current,
            }),
            atBottom,
          });
        setShowScrollTop(false);
        userScrolledUpRef.current = nextFollowState.userScrolledUp;
      }
    });
  }, []);

  const requestScrollToBottom = useCallback(
    (
      mode: AutoScrollMode = "default",
      options?: { clearManualDetachFromStream?: boolean },
    ) => {
      const isHistoryFinalizeMode = mode === "history-finalize";
      const currentFollowState = createMessageScrollFollowState({
        userScrolledUp: userScrolledUpRef.current,
        autoScrollActive: autoScrollActiveRef.current,
        streamLockActive: streamLockActiveRef.current,
        manualDetachFromStream: manualDetachFromStreamRef.current,
      });
      const clearManualDetachFromStream =
        options?.clearManualDetachFromStream ?? false;
      const nextFollowState = getNextMessageScrollFollowStateForBottomScroll({
        state: currentFollowState,
        streamingAssistantActive: streamingAssistantActiveRef.current,
        clearManualDetachFromStream,
      });

      if (
        nextFollowState === currentFollowState &&
        currentFollowState.manualDetachFromStream &&
        !clearManualDetachFromStream
      ) {
        return;
      }

      userScrolledUpRef.current = nextFollowState.userScrolledUp;
      autoScrollActiveRef.current = nextFollowState.autoScrollActive;
      streamLockActiveRef.current = nextFollowState.streamLockActive;
      manualDetachFromStreamRef.current =
        nextFollowState.manualDetachFromStream;
      forceScrollerToPhysicalBottom({
        scroller: virtuosoScrollerRef.current,
        footer: messagesEndRef.current,
      });
      ignoreProgrammaticScrollUntilRef.current = Date.now() + 120;
      scrollCleanupRef.current?.();
      scrollCleanupRef.current = startVirtuosoScrollToBottom({
        virtuoso: virtuosoRef.current,
        scroller: virtuosoScrollerRef.current,
        footer: messagesEndRef.current,
        preferPhysicalBottom: true,
        intervalMs: isMobileViewport ? (isHistoryFinalizeMode ? 24 : 20) : 16,
        maxAttempts: isMobileViewport
          ? isHistoryFinalizeMode
            ? 24
            : 8
          : isHistoryFinalizeMode
            ? 90
            : 15,
        observeLayoutChanges: true,
        resizeObserverTarget:
          virtuosoScrollerRef.current?.firstElementChild ??
          virtuosoScrollerRef.current,
        maxDurationMs: isMobileViewport
          ? isHistoryFinalizeMode
            ? 1200
            : 240
          : isHistoryFinalizeMode
            ? 1800
            : 500,
        settleWindowMs: isMobileViewport
          ? isHistoryFinalizeMode
            ? 140
            : 96
          : isHistoryFinalizeMode
            ? 180
            : 120,
        keepAliveWhile: () =>
          streamLockActiveRef.current && streamingAssistantActiveRef.current,
        shouldAbort: () => userScrolledUpRef.current,
        onAutoScroll: () => {
          ignoreProgrammaticScrollUntilRef.current = Date.now() + 80;
        },
        onComplete: () => {
          autoScrollActiveRef.current = false;
        },
      });
    },
    [isMobileViewport],
  );

  const scrollToBottom = useCallback(() => {
    requestScrollToBottom("default", { clearManualDetachFromStream: true });
  }, [requestScrollToBottom]);

  const scrollToTop = useCallback(() => {
    userScrolledUpRef.current = true;
    autoScrollActiveRef.current = false;
    streamLockActiveRef.current = false;
    pendingHistoryScrollRef.current = false;
    virtuosoRef.current?.scrollTo({
      top: 0,
      behavior: "auto",
    });
    setShowScrollTop(false);
  }, []);

  useEffect(() => {
    const scroller = virtuosoScrollerRef.current;
    if (!scroller) return;

    const lastScrollTop = { value: 0 };
    const lastScrollTime = { value: 0 };
    let touchStartY: number | null = null;
    let timer: ReturnType<typeof setTimeout> | null = null;

    const applyFollowState = (
      nextFollowState: ReturnType<
        typeof getNextMessageScrollFollowStateForUserScroll
      >,
    ) => {
      const stoppedAutoScroll =
        nextFollowState.autoScrollActive !== autoScrollActiveRef.current;
      userScrolledUpRef.current = nextFollowState.userScrolledUp;
      autoScrollActiveRef.current = nextFollowState.autoScrollActive;
      streamLockActiveRef.current = nextFollowState.streamLockActive;
      manualDetachFromStreamRef.current =
        nextFollowState.manualDetachFromStream;
      if (stoppedAutoScroll) {
        pendingHistoryScrollRef.current = false;
      }
    };

    const detachFromUserGesture = (
      transition: (args: {
        state: ReturnType<typeof createMessageScrollFollowState>;
        isMobileViewport: boolean;
        streamingAssistantActive: boolean;
      }) => ReturnType<typeof createMessageScrollFollowState>,
    ) => {
      const currentState = createMessageScrollFollowState({
        userScrolledUp: userScrolledUpRef.current,
        autoScrollActive: autoScrollActiveRef.current,
        streamLockActive: streamLockActiveRef.current,
        manualDetachFromStream: manualDetachFromStreamRef.current,
      });
      const nextFollowState = transition({
        state: currentState,
        isMobileViewport,
        streamingAssistantActive: streamingAssistantActiveRef.current,
      });

      if (nextFollowState === currentState) {
        return;
      }

      applyFollowState(nextFollowState);
      ignoreProgrammaticScrollUntilRef.current = 0;
      scrollCleanupRef.current?.();
      scrollCleanupRef.current = null;
    };

    const handleScroll = () => {
      const now = Date.now();
      const scrollTop = scroller.scrollTop;
      const dt = now - lastScrollTime.value;
      const dScroll = lastScrollTop.value - scrollTop;
      const upwardScrollPx = Math.max(0, dScroll);
      const programmaticScroll =
        now <= ignoreProgrammaticScrollUntilRef.current;
      const movedUp = scrollTop < lastScrollTop.value - 2;
      const isAwayFromBottom =
        scrollTop + scroller.clientHeight <
        scroller.scrollHeight - awayFromBottomThresholdPx;

      const nextFollowState = getNextMessageScrollFollowStateForUserScroll({
        state: createMessageScrollFollowState({
          userScrolledUp: userScrolledUpRef.current,
          autoScrollActive: autoScrollActiveRef.current,
          streamLockActive: streamLockActiveRef.current,
          manualDetachFromStream: manualDetachFromStreamRef.current,
        }),
        isMobileViewport,
        streamingAssistantActive: streamingAssistantActiveRef.current,
        programmaticScroll,
        movedUp,
        isAwayFromBottom,
        deltaScrollPx: upwardScrollPx,
        scrollTop,
      });
      applyFollowState(nextFollowState);

      if (dt < 300 && dScroll > 30 && scrollTop > 200) {
        setShowScrollTop(true);
        userScrolledUpRef.current = true;
        autoScrollActiveRef.current = false;
        streamLockActiveRef.current = false;
        pendingHistoryScrollRef.current = false;
        if (timer) clearTimeout(timer);
        timer = setTimeout(() => setShowScrollTop(false), 3000);
      } else if (scrollTop < 200) {
        setShowScrollTop(false);
      }

      lastScrollTop.value = scrollTop;
      lastScrollTime.value = now;
    };

    const handleTouchStart = (event: TouchEvent) => {
      touchStartY = event.touches[0]?.clientY ?? null;
      detachFromUserGesture(getNextMessageScrollFollowStateForUserIntent);
    };

    const handleTouchMove = (event: TouchEvent) => {
      if (!isMobileViewport || touchStartY === null) {
        return;
      }

      const currentTouchY = event.touches[0]?.clientY;
      if (typeof currentTouchY !== "number") {
        return;
      }

      const upwardGestureDeltaPx = touchStartY - currentTouchY;
      if (upwardGestureDeltaPx <= 6) {
        return;
      }

      detachFromUserGesture(getNextMessageScrollFollowStateForUserGesture);
      touchStartY = currentTouchY;
    };

    const resetTouchTracking = () => {
      touchStartY = null;
    };

    scroller.addEventListener("scroll", handleScroll, { passive: true });
    scroller.addEventListener("touchstart", handleTouchStart, {
      passive: true,
    });
    scroller.addEventListener("touchmove", handleTouchMove, {
      passive: true,
    });
    scroller.addEventListener("touchend", resetTouchTracking, {
      passive: true,
    });
    scroller.addEventListener("touchcancel", resetTouchTracking, {
      passive: true,
    });
    return () => {
      scroller.removeEventListener("scroll", handleScroll);
      scroller.removeEventListener("touchstart", handleTouchStart);
      scroller.removeEventListener("touchmove", handleTouchMove);
      scroller.removeEventListener("touchend", resetTouchTracking);
      scroller.removeEventListener("touchcancel", resetTouchTracking);
      if (timer) clearTimeout(timer);
    };
  }, [awayFromBottomThresholdPx, isMobileViewport, messages.length]);

  useEffect(() => {
    if (!isMobileViewport || typeof window === "undefined") {
      return;
    }

    const viewport = window.visualViewport;
    if (!viewport) {
      return;
    }

    let previousHeight = viewport.height;
    const handleViewportChange = () => {
      if (isLoadingHistoryRef.current) {
        return;
      }

      const heightChanged = Math.abs(viewport.height - previousHeight) > 4;

      previousHeight = viewport.height;

      if (!heightChanged) {
        return;
      }

      if (
        !shouldAutoScrollAfterViewportChange({
          scroller: virtuosoScrollerRef.current,
          bottomBreathingRoomPx,
          userScrolledUp: userScrolledUpRef.current,
          autoScrollActive: autoScrollActiveRef.current,
          isNearBottom: isNearBottomRef.current,
        })
      ) {
        return;
      }

      cancelAnimationFrame(viewportResizeRafRef.current);
      viewportResizeRafRef.current = requestAnimationFrame(() => {
        requestScrollToBottom("default");
      });
    };

    viewport.addEventListener("resize", handleViewportChange);

    return () => {
      viewport.removeEventListener("resize", handleViewportChange);
      cancelAnimationFrame(viewportResizeRafRef.current);
    };
  }, [bottomBreathingRoomPx, isMobileViewport, requestScrollToBottom]);

  useEffect(() => {
    if (!isLoadingHistory) {
      historyLoadActiveRef.current = false;
      historyScrollArmedRef.current = false;
      return;
    }

    if (!historyLoadActiveRef.current) {
      historyLoadActiveRef.current = true;
      historyScrollArmedRef.current = false;
      pendingHistoryScrollRef.current = false;
    }

    if (
      shouldArmPendingHistoryScroll({
        isLoadingHistory,
        sessionId,
        historyScrollArmed: historyScrollArmedRef.current,
      })
    ) {
      pendingHistoryScrollRef.current = !externalNavigationToken;
      historyScrollArmedRef.current = true;
    }
  }, [sessionId, externalNavigationToken, isLoadingHistory]);

  useEffect(() => {
    if (!isLoadingHistory && messages.length === 0) {
      pendingHistoryScrollRef.current = false;
    }

    if (
      shouldFinalizeHistoryLoadScroll({
        pendingHistoryScroll: pendingHistoryScrollRef.current,
        isLoadingHistory,
        messageCount: messages.length,
      })
    ) {
      let raf1 = 0;
      let raf2 = 0;
      let settled = false;

      const tryScroll = () => {
        if (settled) return;
        if (!virtuosoRef.current || !virtuosoScrollerRef.current) {
          raf1 = requestAnimationFrame(() => {
            raf2 = requestAnimationFrame(tryScroll);
          });
          return;
        }
        settled = true;
        pendingHistoryScrollRef.current = false;
        requestScrollToBottom("history-finalize");
      };

      raf1 = requestAnimationFrame(() => {
        raf2 = requestAnimationFrame(tryScroll);
      });
      return () => {
        settled = true;
        cancelAnimationFrame(raf1);
        cancelAnimationFrame(raf2);
      };
    }
  }, [isLoadingHistory, messages.length, requestScrollToBottom]);

  useEffect(() => {
    const previousMessages = previousMessagesRef.current;
    const shouldMaintainStreamLock = streamLockActiveRef.current;

    let effectiveIsNearBottom = isNearBottomRef.current;
    if (!effectiveIsNearBottom && !userScrolledUpRef.current) {
      const scroller = virtuosoScrollerRef.current;
      if (scroller) {
        effectiveIsNearBottom =
          scroller.scrollTop + scroller.clientHeight >=
          scroller.scrollHeight - autoScrollResumeThresholdPx;
      }
    }

    const messageUpdateAction = getMessageUpdateScrollAction({
      previousMessages,
      nextMessages: messages,
      state: createMessageScrollFollowState({
        userScrolledUp: userScrolledUpRef.current,
        autoScrollActive: autoScrollActiveRef.current,
        streamLockActive: streamLockActiveRef.current,
        manualDetachFromStream: manualDetachFromStreamRef.current,
      }),
      isNearBottom: effectiveIsNearBottom,
      isLoadingHistory,
      shouldMaintainStreamLock,
    });

    if (messageUpdateAction === "scroll-to-bottom") {
      scrollToBottom();
    } else if (messageUpdateAction === "request-scroll-to-bottom") {
      requestScrollToBottom("default");
    }

    if (!hasStreamingAssistantMessage) {
      streamLockActiveRef.current = false;
    }

    previousMessagesRef.current = messages;
  }, [
    messages,
    requestScrollToBottom,
    scrollToBottom,
    autoScrollResumeThresholdPx,
    hasStreamingAssistantMessage,
    isLoadingHistory,
  ]);

  useEffect(() => {
    if (externalNavigationToken) {
      pendingExternalNavigationRef.current = {
        token: externalNavigationToken,
        targetFile: externalNavigationTargetFile ?? null,
        scrollToBottom: externalScrollToBottom,
      };
    }
  }, [
    externalNavigationToken,
    externalNavigationTargetFile,
    externalScrollToBottom,
  ]);

  useEffect(() => {
    const pendingExternalNavigation = pendingExternalNavigationRef.current;
    if (!pendingExternalNavigation || messages.length === 0) {
      return;
    }

    if (!virtuosoRef.current || !virtuosoScrollerRef.current) {
      return;
    }

    if (pendingExternalNavigation.targetFile) {
      if (
        pendingExternalNavigation.targetFile.traceId &&
        externalNavigationTargetRunPending &&
        !externalNavigationTargetRunId
      ) {
        return;
      }

      const runMatch = findExternalNavigationMatchForRunId(
        messages,
        externalNavigationTargetRunId,
        pendingExternalNavigation.targetFile,
      );
      const runMessageIndex = findMessageIndexForRunId(
        messages,
        externalNavigationTargetRunId,
      );
      const contentMatch =
        !runMatch && runMessageIndex === -1 && !externalNavigationTargetRunId
          ? findMessageIndexForExternalNavigation(
              messages,
              pendingExternalNavigation.targetFile,
            )
          : null;

      if (runMessageIndex === -1 && !contentMatch) {
        if (!isLoadingHistory) {
          pendingExternalNavigationRef.current = null;
        }
        return;
      }

      userScrolledUpRef.current = true;
      autoScrollActiveRef.current = false;
      streamLockActiveRef.current = false;
      pendingHistoryScrollRef.current = false;
      ignoreProgrammaticScrollUntilRef.current = Date.now() + 120;
      anchorScrollCleanupRef.current?.();

      const resolvedMessageIndex =
        runMatch?.messageIndex ??
        (runMessageIndex !== -1
          ? runMessageIndex
          : contentMatch?.messageIndex ?? -1);
      const resolvedMatch =
        runMatch ??
        (runMessageIndex !== -1
          ? findRevealPartMatchInMessage(
              messages[resolvedMessageIndex],
              pendingExternalNavigation.targetFile,
            )
          : contentMatch);
      const matchedPartIndex = resolvedMatch?.partIndex ?? -1;
      const shouldKeepPending = shouldKeepExternalNavigationPending({
        runMessageIndex,
        matchedPartIndex,
      });
      const shouldDeferScroll = shouldDeferExternalNavigationScroll({
        runMessageIndex,
        matchedPartIndex,
      });
      const shouldFallbackToMessage =
        shouldScrollExternalNavigationFallbackToMessage({
          runMessageIndex,
          matchedPartIndex,
        });

      if (!shouldKeepPending) {
        pendingExternalNavigationRef.current = null;
      }
      const fallbackMessageAnchorId = createMessageAnchorId(
        messages[resolvedMessageIndex]!.id,
      );
      const exactAnchorId = resolvedMatch?.anchorId;
      const subagentChain = resolvedMatch?.subagentChain;
      const shouldTargetExactElement =
        matchedPartIndex !== -1 && typeof exactAnchorId === "string";
      let hasAnimatedToMessage = false;
      let lastHighlightedElement: HTMLElement | null = null;
      const resolveTargetElement = createExternalNavigationElementResolver({
        shouldTargetExactElement:
          shouldTargetExactElement && !shouldFallbackToMessage,
        scrollToMessageIndex: () => {
          virtuosoRef.current?.scrollToIndex({
            index: resolvedMessageIndex,
            align: "center",
            behavior: hasAnimatedToMessage ? "auto" : "smooth",
          });
          hasAnimatedToMessage = true;
        },
        getExactElement: () =>
          exactAnchorId ? document.getElementById(exactAnchorId) : null,
        getFallbackElement: () =>
          document.getElementById(fallbackMessageAnchorId),
      });

      anchorScrollCleanupRef.current = scrollElementIntoViewWithRetries({
        getElement: () => {
          ensureSubagentPanelsOpen(subagentChain);
          const element = resolveTargetElement();
          if (element && element !== lastHighlightedElement) {
            highlightCleanupRef.current?.();
            highlightCleanupRef.current = highlightElementForExternalNavigation(
              {
                element,
              },
            );
            focusElementForExternalNavigation({
              element,
            });
            lastHighlightedElement = element;
          }
          return element;
        },
        getScroller:
          shouldTargetExactElement && !subagentChain?.length
            ? () => virtuosoScrollerRef.current
            : undefined,
        topOffsetPx: 20,
        tolerancePx: 4,
        settleAttempts: 3,
        maxAttempts: subagentChain?.length ? 36 : 24,
        behavior: "smooth",
        align: "center",
      });

      if (shouldDeferScroll) {
        return;
      }
      return;
    }

    if (pendingExternalNavigation.scrollToBottom) {
      if (isLoadingHistory) {
        return;
      }
      pendingExternalNavigationRef.current = null;
      requestScrollToBottom("default");
    }
  }, [
    messages,
    requestScrollToBottom,
    isLoadingHistory,
    externalNavigationTargetRunId,
    externalNavigationTargetRunPending,
    externalNavigationTargetFile,
  ]);

  useEffect(() => {
    return () => {
      cancelAnimationFrame(rafRef.current);
      cancelAnimationFrame(viewportResizeRafRef.current);
      scrollCleanupRef.current?.();
      anchorScrollCleanupRef.current?.();
      highlightCleanupRef.current?.();
    };
  }, []);

  return {
    messagesContainerRef,
    virtuosoRef,
    virtuosoScrollerRef,
    messagesEndRef,
    isNearBottom,
    showScrollTop,
    handleVirtuosoAtBottomChange,
    scrollToBottom,
    scrollToTop,
  };
}
