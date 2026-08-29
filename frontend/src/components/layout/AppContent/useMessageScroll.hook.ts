import {
  useRef,
  useEffect,
  useLayoutEffect,
  useMemo,
  useState,
  useCallback,
} from "react";
import type { VirtuosoHandle } from "react-virtuoso";
import type { Message } from "../../../types";
import type { ExternalNavigationTargetFile } from "./externalNavigationState";
import { wrapVirtuosoHandleForDataIndices } from "./virtuosoIndexOffset";
import {
  forceVirtuosoToBottom,
  getScrollToBottomTimingOptions,
  didLatestStreamingAssistantFinish,
  shouldAutoScrollAfterViewportChange,
  shouldIgnoreUnexpectedTopJumpDuringBottomLock,
  getUnexpectedTopJumpRecoveryUntilAfterUserIntent,
  startVirtuosoScrollToBottom,
  createWheelIntentAccumulator,
  nextWheelIntentState,
  type ScrollToBottomTimingMode,
} from "./messageScrollUtils";
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
} from "./useMessageScroll.followState";
import { setStreamFollowSignal } from "../../chat/streamFollowSignal";

interface UseMessageScrollReturn {
  messagesContainerRef: React.RefObject<HTMLDivElement | null>;
  virtuosoRef: React.RefObject<VirtuosoHandle | null>;
  virtuosoScrollerRef: React.RefObject<HTMLDivElement | null>;
  /** Feed this from the Virtuoso Scroller ref callback. The scroller element is
   *  tracked in state so wheel/touch/scroll listeners re-bind when the list
   *  remounts (e.g. the session key swap after switching into a conversation). */
  handleVirtuosoScrollerElementChange: (element: HTMLDivElement | null) => void;
  messagesEndRef: React.RefObject<HTMLDivElement | null>;
  isNearBottom: boolean;
  isNearTop: boolean;
  /** Ref that is true when the user has explicitly scrolled up during streaming and
   *  should not be pulled back to the bottom by followOutput. */
  manualDetachFromStreamRef: React.RefObject<boolean>;
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
  historyLoadGeneration = 0,
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

  // 外部导航按数据索引调用 scrollToIndex；scrollToIndex 原生就期望数据
  // 索引（与 rangeChanged 的绝对索引不对称），适配器只做语义透传
  const dataIndexVirtuosoRef = useMemo<React.RefObject<VirtuosoHandle | null>>(
    () => ({
      get current() {
        const handle = virtuosoRef.current;
        return handle ? wrapVirtuosoHandleForDataIndices(handle) : null;
      },
    }),
    [virtuosoRef],
  );
  // The scroller DOM element is tracked in state (not just a ref) because the
  // Virtuoso list remounts on session-key swaps while messages.length may stay
  // constant; listeners bound by an effect keyed on messages.length would stay
  // attached to the detached element and the user could never detach from the
  // stream-follow auto scroll.
  const [virtuosoScrollerElement, setVirtuosoScrollerElement] =
    useState<HTMLDivElement | null>(null);
  const handleVirtuosoScrollerElementChange = useCallback(
    (element: HTMLDivElement | null) => {
      virtuosoScrollerRef.current = element;
      setVirtuosoScrollerElement(element);
    },
    [],
  );
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
    historyLoadGeneration,
  });
  const isNearBottomRef = useRef(true);

  const userScrolledUpRef = useRef(false);
  const autoScrollActiveRef = useRef(false);
  const ignoreProgrammaticScrollUntilRef = useRef(0);
  const recoverUnexpectedTopJumpUntilRef = useRef(0);
  const streamLockActiveRef = useRef(false);
  const manualDetachFromStreamRef = useRef(false);
  const streamingAssistantActiveRef = useRef(false);
  const pendingHistoryScrollRef = useRef<number | null>(null);
  const armedHistoryGenerationRef = useRef(0);
  const completedHistoryGenerationRef = useRef(0);
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
    pendingHistoryScrollRef.current = null;
    ignoreProgrammaticScrollUntilRef.current = 0;
    recoverUnexpectedTopJumpUntilRef.current = 0;
    isNearBottomRef.current = resetState.isNearBottom;
    previousMessagesRef.current = messages;

    setIsNearBottom(resetState.isNearBottom);
    setIsNearTop(true);
  }, [isLoadingHistory, messages, sessionId]);

  const handleVirtuosoAtBottomChange = useCallback((atBottom: boolean) => {
    cancelAnimationFrame(rafRef.current);
    rafRef.current = requestAnimationFrame(() => {
      setIsNearBottom(atBottom);
      isNearBottomRef.current = atBottom;
      // 供深层组件（自动开面板等）同步读取：用户是否离开底部在读历史
      setStreamFollowSignal({
        nearBottom: atBottom,
        detached: manualDetachFromStreamRef.current,
      });
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
        onComplete?: (reason: "settled" | "aborted" | "max-attempts") => void;
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
        onComplete: (reason) => {
          autoScrollActiveRef.current = false;
          recoverUnexpectedTopJumpUntilRef.current =
            Date.now() + timing.observeAfterSettleMs;
          options?.onComplete?.(reason);
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
    pendingHistoryScrollRef.current = null;
    recoverUnexpectedTopJumpUntilRef.current = 0;
    virtuosoRef.current?.scrollTo({
      top: 0,
      behavior: "auto",
    });
  }, []);

  useEffect(() => {
    const scroller = virtuosoScrollerElement;
    if (!scroller) return;

    // 基线取当前真实位置：监听会随 messages.length 重绑（流式追加即重绑），
    // 归零起算会漏掉重绑后第一次真实上滚的 movedUp 判定
    const lastScrollTop = { value: scroller.scrollTop };
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
        pendingHistoryScrollRef.current = null;
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
      // 8px 以内的上移视为上方内容回流抖动（折叠区收起、代码块重排），不算用户上滚
      const movedUp = scrollTop < lastScrollTop.value - 8;
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

    // wheel 上滚意图累计器（触控板惯性微滑判定，见 nextWheelIntentState）
    let wheelIntentAccum = createWheelIntentAccumulator();

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
      // 触控板惯性是一串 <6px 的连续微上滑：单事件阈值拦不住会被
      // 底部锁定逐个粘回；按时间窗累计判定明确的上滚意图后才脱钉
      const intent = nextWheelIntentState(
        wheelIntentAccum,
        event.deltaY,
        Date.now(),
      );
      wheelIntentAccum = intent.state;
      if (!intent.detach) {
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
  }, [
    awayFromBottomThresholdPx,
    isMobileViewport,
    messages.length,
    virtuosoScrollerElement,
  ]);

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

  useLayoutEffect(() => {
    if (
      shouldArmPendingHistoryScroll({
        isLoadingHistory,
        historyScrollArmed:
          armedHistoryGenerationRef.current === historyLoadGeneration,
      })
    ) {
      armedHistoryGenerationRef.current = historyLoadGeneration;
      pendingHistoryScrollRef.current = externalNavigationToken
        ? null
        : historyLoadGeneration;
    }
  }, [externalNavigationToken, historyLoadGeneration, isLoadingHistory]);

  useLayoutEffect(() => {
    const previousHistoryLoadSignature =
      previousHistoryLoadSignatureRef.current;
    previousHistoryLoadSignatureRef.current = {
      sessionId,
      messageCount: messages.length,
      historyLoadGeneration,
    };

    if (
      shouldInferBatchedHistoryLoadReady({
        previousSessionId: previousHistoryLoadSignature.sessionId,
        sessionId,
        previousMessageCount: previousHistoryLoadSignature.messageCount,
        messageCount: messages.length,
        previousHistoryLoadGeneration:
          previousHistoryLoadSignature.historyLoadGeneration,
        historyLoadGeneration,
        isLoadingHistory,
        externalNavigationToken,
      })
    ) {
      armedHistoryGenerationRef.current = historyLoadGeneration;
      pendingHistoryScrollRef.current = historyLoadGeneration;
    }

    if (!isLoadingHistory && messages.length === 0) {
      pendingHistoryScrollRef.current = null;
    }

    const isCurrentHistoryCompletion =
      !isLoadingHistory &&
      messages.length > 0 &&
      armedHistoryGenerationRef.current === historyLoadGeneration &&
      completedHistoryGenerationRef.current !== historyLoadGeneration;

    if (isCurrentHistoryCompletion) {
      completedHistoryGenerationRef.current = historyLoadGeneration;
      // The message-update effect runs after this layout effect. Mark the
      // reconstructed batch as consumed so it is not mistaken for a newly
      // streamed assistant message and scrolled a second time.
      previousMessagesRef.current = messages;
    }

    if (
      isCurrentHistoryCompletion &&
      shouldFinalizeHistoryLoadScroll({
        pendingHistoryScroll: pendingHistoryScrollRef.current !== null,
        isLoadingHistory,
        messageCount: messages.length,
      })
    ) {
      const pendingGeneration = pendingHistoryScrollRef.current;
      pendingHistoryScrollRef.current = null;
      const virtuoso = virtuosoRef.current;
      if (
        pendingGeneration !== historyLoadGeneration ||
        externalNavigationToken ||
        !virtuoso
      ) {
        return;
      }
      virtuoso.scrollToIndex({
        index: "LAST",
        align: "end",
        behavior: "auto",
      });
    }
  }, [
    externalNavigationToken,
    historyLoadGeneration,
    isLoadingHistory,
    messages,
    messages.length,
    sessionId,
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
    virtuosoRef: dataIndexVirtuosoRef,
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
      // These cleanup callbacks are assigned after mount by external navigation retries.
      // Read the latest refs on unmount so in-flight scroll/highlight work is cancelled.
      // eslint-disable-next-line react-hooks/exhaustive-deps
      anchorScrollCleanupRef.current?.();
      // eslint-disable-next-line react-hooks/exhaustive-deps
      highlightCleanupRef.current?.();
    };
  }, []);

  return {
    messagesContainerRef,
    virtuosoRef,
    virtuosoScrollerRef,
    handleVirtuosoScrollerElementChange,
    messagesEndRef,
    isNearBottom,
    isNearTop,
    manualDetachFromStreamRef,
    handleVirtuosoAtBottomChange,
    scrollToBottom,
    scrollToTop,
  };
}
