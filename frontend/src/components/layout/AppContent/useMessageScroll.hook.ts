import {
  useRef,
  useEffect,
  useLayoutEffect,
  useState,
  useCallback,
} from "react";
import type { VirtuosoHandle } from "react-virtuoso";
import type { Message } from "../../../types";
import type { ExternalNavigationTargetFile } from "./externalNavigationState";
import {
  forceVirtuosoToBottom,
  getScrollToBottomTimingOptions,
  didLatestStreamingAssistantFinish,
  shouldAutoScrollAfterViewportChange,
  shouldIgnoreUnexpectedTopJumpDuringBottomLock,
  getUnexpectedTopJumpRecoveryUntilAfterUserIntent,
  startVirtuosoScrollToBottom,
  type ScrollToBottomTimingMode,
} from "./messageScrollUtils";
import { useMessageScrollHistorySettling } from "./useMessageScroll.historySettling";
import { getMessageScrollViewportState } from "./useMessageScroll.viewport";
import { useMessageScrollExternalNavigationEffect } from "./useMessageScroll.externalNavigationEffect";
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
  shouldInferBatchedHistoryLoadReady,
  shouldStartHistoryScrollSettling,
} from "./useMessageScroll.followState";

interface UseMessageScrollReturn {
  messagesContainerRef: React.RefObject<HTMLDivElement | null>;
  virtuosoRef: React.RefObject<VirtuosoHandle | null>;
  virtuosoScrollerRef: React.RefObject<HTMLDivElement | null>;
  messagesEndRef: React.RefObject<HTMLDivElement | null>;
  isNearBottom: boolean;
  isNearTop: boolean;
  isHistoryScrollSettling: boolean;
  handleVirtuosoAtBottomChange: (atBottom: boolean) => void;
  scrollToBottom: () => void;
  scrollToTop: () => void;
}

export function useMessageScroll(
  messages: Pick<Message, "id" | "role" | "isStreaming" | "parts" | "runId">[],
  sessionId?: string | null,
  externalNavigationToken?: string | null,
  externalNavigationTargetFile?: ExternalNavigationTargetFile | null,
  externalNavigationTargetRunId?: string | null,
  externalNavigationTargetRunPending = false,
  externalScrollToBottom = false,
  isLoadingHistory = false,
  sessionBottomScrollToken?: string | null,
): UseMessageScrollReturn {
  const {
    isMobileViewport,
    bottomBreathingRoomPx,
    awayFromBottomThresholdPx,
    autoScrollResumeThresholdPx,
  } = getMessageScrollViewportState();
  const messagesContainerRef = useRef<HTMLDivElement>(null);
  const virtuosoRef = useRef<VirtuosoHandle>(null);
  const virtuosoScrollerRef = useRef<HTMLDivElement>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const [isNearBottom, setIsNearBottom] = useState(true);
  const [isNearTop, setIsNearTop] = useState(true);
  const {
    isHistoryScrollSettling,
    clearHistoryScrollSettling,
    startHistoryScrollSettling,
  } = useMessageScrollHistorySettling();
  const rafRef = useRef<number>(0);
  const viewportResizeRafRef = useRef<number>(0);
  const scrollCleanupRef = useRef<(() => void) | null>(null);
  const anchorScrollCleanupRef = useRef<(() => void) | null>(null);
  const highlightCleanupRef = useRef<(() => void) | null>(null);
  const pendingExternalNavigationRef = useRef<{
    token: string;
    targetFile: ExternalNavigationTargetFile | null;
    scrollToBottom: boolean;
    targetRunId: string | null;
  } | null>(null);
  const previousSessionIdRef = useRef(sessionId);
  const previousMessagesRef = useRef(messages);
  const previousHistoryLoadSignatureRef = useRef({
    sessionId,
    messageCount: messages.length,
  });
  const isNearBottomRef = useRef(true);

  const userScrolledUpRef = useRef(false);
  const autoScrollActiveRef = useRef(false);
  const ignoreProgrammaticScrollUntilRef = useRef(0);
  const recoverUnexpectedTopJumpUntilRef = useRef(0);
  const streamLockActiveRef = useRef(false);
  const manualDetachFromStreamRef = useRef(false);
  const streamingAssistantActiveRef = useRef(false);
  const pendingHistoryScrollRef = useRef(false);
  const historyLoadActiveRef = useRef(isLoadingHistory);
  const historyScrollArmedRef = useRef(false);
  const isLoadingHistoryRef = useRef(isLoadingHistory);
  const handledSessionBottomScrollTokenRef = useRef<string | null>(null);

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
    recoverUnexpectedTopJumpUntilRef.current = 0;
    isNearBottomRef.current = resetState.isNearBottom;
    previousMessagesRef.current = messages;
    historyLoadActiveRef.current = isLoadingHistory;
    clearHistoryScrollSettling();

    setIsNearBottom(resetState.isNearBottom);
    setIsNearTop(true);
  }, [clearHistoryScrollSettling, isLoadingHistory, messages, sessionId]);

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
        userScrolledUpRef.current = nextFollowState.userScrolledUp;
      }
    });
  }, []);

  const requestScrollToBottom = useCallback(
    (
      mode: ScrollToBottomTimingMode = "default",
      options?: {
        clearManualDetachFromStream?: boolean;
        onInitialSettle?: () => void;
        onComplete?: () => void;
      },
    ) => {
      const timing = getScrollToBottomTimingOptions({
        isMobileViewport,
        mode,
      });
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
      forceVirtuosoToBottom({
        virtuoso: virtuosoRef.current,
        scroller: virtuosoScrollerRef.current,
        footer: messagesEndRef.current,
      });
      ignoreProgrammaticScrollUntilRef.current = Date.now() + 120;
      recoverUnexpectedTopJumpUntilRef.current =
        Date.now() + timing.observeAfterSettleMs;
      scrollCleanupRef.current?.();
      scrollCleanupRef.current = startVirtuosoScrollToBottom({
        virtuoso: virtuosoRef.current,
        scroller: virtuosoScrollerRef.current,
        footer: messagesEndRef.current,
        preferPhysicalBottom: true,
        intervalMs: timing.intervalMs,
        maxAttempts: timing.maxAttempts,
        observeLayoutChanges: true,
        resizeObserverTarget:
          virtuosoScrollerRef.current?.firstElementChild ??
          virtuosoScrollerRef.current,
        maxDurationMs: timing.maxDurationMs,
        settleWindowMs: timing.settleWindowMs,
        observeAfterSettleMs: timing.observeAfterSettleMs,
        keepAliveWhile: () =>
          streamLockActiveRef.current && streamingAssistantActiveRef.current,
        shouldAbort: () => userScrolledUpRef.current,
        onAutoScroll: () => {
          ignoreProgrammaticScrollUntilRef.current = Date.now() + 80;
          recoverUnexpectedTopJumpUntilRef.current =
            Date.now() + timing.observeAfterSettleMs;
        },
        onInitialSettle: () => {
          options?.onInitialSettle?.();
        },
        onComplete: () => {
          autoScrollActiveRef.current = false;
          recoverUnexpectedTopJumpUntilRef.current =
            Date.now() + timing.observeAfterSettleMs;
          options?.onComplete?.();
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
    recoverUnexpectedTopJumpUntilRef.current = 0;
    virtuosoRef.current?.scrollTo({
      top: 0,
      behavior: "auto",
    });
  }, []);

  useEffect(() => {
    const scroller = virtuosoScrollerRef.current;
    if (!scroller) return;

    const lastScrollTop = { value: 0 };
    const lastScrollTime = { value: 0 };
    let touchStartY: number | null = null;

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

      recoverUnexpectedTopJumpUntilRef.current =
        getUnexpectedTopJumpRecoveryUntilAfterUserIntent({
          recoverUntil: recoverUnexpectedTopJumpUntilRef.current,
          now: Date.now(),
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
      const dScroll = lastScrollTop.value - scrollTop;
      const upwardScrollPx = Math.max(0, dScroll);
      const programmaticScroll =
        now <= ignoreProgrammaticScrollUntilRef.current;
      const movedUp = scrollTop < lastScrollTop.value - 2;
      const isAwayFromBottom =
        scrollTop + scroller.clientHeight <
        scroller.scrollHeight - awayFromBottomThresholdPx;

      if (
        shouldIgnoreUnexpectedTopJumpDuringBottomLock({
          scrollTop,
          clientHeight: scroller.clientHeight,
          scrollHeight: scroller.scrollHeight,
          autoScrollActive: autoScrollActiveRef.current,
          recentlyBottomLocked: now <= recoverUnexpectedTopJumpUntilRef.current,
          userScrolledUp: userScrolledUpRef.current,
          manualDetachActive: manualDetachFromStreamRef.current,
        })
      ) {
        forceVirtuosoToBottom({
          virtuoso: virtuosoRef.current,
          scroller,
          footer: messagesEndRef.current,
        });
        ignoreProgrammaticScrollUntilRef.current = now + 120;
        setIsNearTop(false);
        lastScrollTop.value = scroller.scrollTop;
        lastScrollTime.value = now;
        return;
      }

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

      setIsNearTop(scrollTop < 200);

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

    const handleWheel = (event: WheelEvent) => {
      if (event.deltaY >= -1) {
        return;
      }

      detachFromUserGesture(getNextMessageScrollFollowStateForUserIntent);
    };

    const resetTouchTracking = () => {
      touchStartY = null;
    };

    scroller.addEventListener("scroll", handleScroll, { passive: true });
    scroller.addEventListener("wheel", handleWheel, { passive: true });
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
      scroller.removeEventListener("wheel", handleWheel);
      scroller.removeEventListener("touchstart", handleTouchStart);
      scroller.removeEventListener("touchmove", handleTouchMove);
      scroller.removeEventListener("touchend", resetTouchTracking);
      scroller.removeEventListener("touchcancel", resetTouchTracking);
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

  useLayoutEffect(() => {
    const previousHistoryLoadSignature =
      previousHistoryLoadSignatureRef.current;
    previousHistoryLoadSignatureRef.current = {
      sessionId,
      messageCount: messages.length,
    };

    if (
      shouldInferBatchedHistoryLoadReady({
        previousSessionId: previousHistoryLoadSignature.sessionId,
        sessionId,
        previousMessageCount: previousHistoryLoadSignature.messageCount,
        messageCount: messages.length,
        isLoadingHistory,
        externalNavigationToken,
      })
    ) {
      pendingHistoryScrollRef.current = true;
    }

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
      if (
        shouldStartHistoryScrollSettling({
          pendingHistoryScroll: pendingHistoryScrollRef.current,
          isLoadingHistory,
          messageCount: messages.length,
          externalNavigationToken,
        })
      ) {
        startHistoryScrollSettling();
      }

      let raf = 0;
      let settled = false;

      const tryScroll = () => {
        if (settled) return;
        if (!virtuosoRef.current || !virtuosoScrollerRef.current) {
          raf = requestAnimationFrame(tryScroll);
          return;
        }
        settled = true;
        pendingHistoryScrollRef.current = false;
        requestScrollToBottom("history-finalize", {
          onComplete: clearHistoryScrollSettling,
        });
      };

      tryScroll();
      return () => {
        settled = true;
        cancelAnimationFrame(raf);
      };
    }
  }, [
    clearHistoryScrollSettling,
    externalNavigationToken,
    isLoadingHistory,
    messages.length,
    requestScrollToBottom,
    sessionId,
    startHistoryScrollSettling,
  ]);

  useEffect(() => {
    if (sessionBottomScrollToken && externalNavigationToken) {
      handledSessionBottomScrollTokenRef.current = sessionBottomScrollToken;
      return;
    }

    if (
      !sessionBottomScrollToken ||
      handledSessionBottomScrollTokenRef.current === sessionBottomScrollToken ||
      messages.length === 0 ||
      isLoadingHistory ||
      externalNavigationToken
    ) {
      return;
    }

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
      handledSessionBottomScrollTokenRef.current = sessionBottomScrollToken;
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
  }, [
    externalNavigationToken,
    isLoadingHistory,
    messages.length,
    requestScrollToBottom,
    sessionBottomScrollToken,
  ]);

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

    if (
      didLatestStreamingAssistantFinish({
        previousMessages,
        nextMessages: messages,
      })
    ) {
      if (messageUpdateAction !== "request-scroll-to-bottom") {
        scrollCleanupRef.current?.();
        scrollCleanupRef.current = null;
      }
      autoScrollActiveRef.current = false;
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

  useMessageScrollExternalNavigationEffect({
    messages,
    isLoadingHistory,
    externalNavigationToken,
    externalNavigationTargetFile,
    externalNavigationTargetRunId,
    externalNavigationTargetRunPending,
    externalScrollToBottom,
    virtuosoRef,
    virtuosoScrollerRef,
    pendingExternalNavigationRef,
    userScrolledUpRef,
    autoScrollActiveRef,
    streamLockActiveRef,
    pendingHistoryScrollRef,
    ignoreProgrammaticScrollUntilRef,
    anchorScrollCleanupRef,
    highlightCleanupRef,
    requestScrollToBottom,
  });

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
    isNearTop,
    isHistoryScrollSettling,
    handleVirtuosoAtBottomChange,
    scrollToBottom,
    scrollToTop,
  };
}
