type ScrollBehaviorMode = "auto" | "smooth";

interface VirtuosoLike {
  autoscrollToBottom?: () => void;
  scrollTo: (args: { top: number; behavior: ScrollBehaviorMode }) => void;
  scrollToIndex?: (args: {
    index: "LAST" | number;
    align?: "center" | "end" | "start";
    behavior?: ScrollBehaviorMode;
  }) => void;
}

interface ScrollerLike {
  scrollTop: number;
  clientHeight: number;
  scrollHeight: number;
}

interface FooterLike {
  scrollIntoView: (args?: {
    behavior?: ScrollBehaviorMode;
    block?: ScrollLogicalPosition;
  }) => void;
}

interface ResizeObserverLike {
  observe: (target: unknown) => void;
  disconnect: () => void;
}

interface StartVirtuosoScrollToBottomOptions {
  virtuoso?: VirtuosoLike | null;
  scroller?: ScrollerLike | null;
  footer?: FooterLike | null;
  preferPhysicalBottom?: boolean;
  intervalMs?: number;
  maxAttempts?: number;
  maxDurationMs?: number;
  settleWindowMs?: number;
  observeLayoutChanges?: boolean;
  resizeObserverFactory?: (callback: () => void) => ResizeObserverLike;
  resizeObserverTarget?: unknown;
  observeAfterSettleMs?: number;
  // Kept for compatibility with older callers. Settling must still require
  // the physical scroll bottom, otherwise the user can still drag lower.
  bottomOffsetPx?: number;
  keepAliveWhile?: () => boolean;
  shouldAbort?: () => boolean;
  onAutoScroll?: () => void;
  onInitialSettle?: () => void;
  onComplete?: (reason: "settled" | "aborted" | "max-attempts") => void;
  resetBudgetOnLayoutChange?: boolean;
}

export interface ScrollMessageLike {
  id: string;
  role?: string;
  isStreaming?: boolean;
}

export type ScrollToBottomTimingMode = "default" | "history-finalize";

export interface ScrollToBottomTimingOptions {
  intervalMs: number;
  maxAttempts: number;
  maxDurationMs: number;
  settleWindowMs: number;
  observeAfterSettleMs: number;
}

export function getAtBottomThresholdPx(isMobileViewport: boolean): number {
  return isMobileViewport ? 120 : 4;
}

export function getScrollToBottomTimingOptions({
  isMobileViewport,
  mode,
}: {
  isMobileViewport: boolean;
  mode: ScrollToBottomTimingMode;
}): ScrollToBottomTimingOptions {
  const isHistoryFinalizeMode = mode === "history-finalize";

  if (isMobileViewport) {
    return {
      intervalMs: isHistoryFinalizeMode ? 24 : 20,
      maxAttempts: isHistoryFinalizeMode ? 24 : 8,
      maxDurationMs: isHistoryFinalizeMode ? 1200 : 240,
      settleWindowMs: isHistoryFinalizeMode ? 140 : 96,
      observeAfterSettleMs: 3600,
    };
  }

  return {
    intervalMs: 16,
    maxAttempts: isHistoryFinalizeMode ? 90 : 15,
    maxDurationMs: isHistoryFinalizeMode ? 1800 : 500,
    settleWindowMs: isHistoryFinalizeMode ? 180 : 120,
    observeAfterSettleMs: 2400,
  };
}

export function getAutoScrollResumeThresholdPx(
  isMobileViewport: boolean,
  bottomBreathingRoomPx: number,
): number {
  return isMobileViewport ? Math.max(120, bottomBreathingRoomPx) : 48;
}

export function getAwayFromBottomThresholdPx(
  isMobileViewport: boolean,
  bottomBreathingRoomPx: number,
): number {
  return isMobileViewport ? Math.max(50, bottomBreathingRoomPx) : 16;
}

export function getMessageListFooterSpacerClass(
  isMobileViewport: boolean,
): string {
  return isMobileViewport
    ? "h-[calc(1.5rem+env(safe-area-inset-bottom))]"
    : "h-8";
}

export function getInitialBottomItemLocation(
  messageCount: number,
): { index: number; align: "end" } | undefined {
  if (messageCount <= 0) {
    return undefined;
  }

  return {
    index: messageCount - 1,
    align: "end",
  };
}

export function getMessageListSessionKey(sessionId?: string | null): string {
  return sessionId ?? "__new_session__";
}

export function hasNewOutgoingMessage(
  previousMessages: ScrollMessageLike[],
  nextMessages: ScrollMessageLike[],
): boolean {
  if (
    nextMessages.length <= previousMessages.length ||
    nextMessages.length - previousMessages.length > 2
  ) {
    return false;
  }

  const appendedMessages = nextMessages.slice(previousMessages.length);
  return appendedMessages[0]?.role === "user";
}

export function didLatestStreamingAssistantFinish({
  previousMessages,
  nextMessages,
}: {
  previousMessages: ScrollMessageLike[];
  nextMessages: ScrollMessageLike[];
}): boolean {
  const previousLatestMessage = previousMessages[previousMessages.length - 1];
  const nextLatestMessage = nextMessages[nextMessages.length - 1];

  return (
    previousLatestMessage?.id === nextLatestMessage?.id &&
    previousLatestMessage?.role === "assistant" &&
    nextLatestMessage?.role === "assistant" &&
    previousLatestMessage.isStreaming === true &&
    nextLatestMessage.isStreaming === false
  );
}

export function shouldAutoScrollForMessageUpdate({
  previousMessages,
  nextMessages,
  userScrolledUp,
  autoScrollActive,
  isNearBottom,
  isLoadingHistory = false,
  shouldMaintainStreamLock = false,
  manualDetachActive = false,
}: {
  previousMessages: ScrollMessageLike[];
  nextMessages: ScrollMessageLike[];
  userScrolledUp: boolean;
  autoScrollActive: boolean;
  isNearBottom: boolean;
  isLoadingHistory?: boolean;
  shouldMaintainStreamLock?: boolean;
  manualDetachActive?: boolean;
}): boolean {
  if (userScrolledUp || nextMessages.length === 0 || isLoadingHistory) {
    return false;
  }

  if (!autoScrollActive && !isNearBottom && !shouldMaintainStreamLock) {
    return false;
  }

  const previousLatestMessage = previousMessages[previousMessages.length - 1];
  const nextLatestMessage = nextMessages[nextMessages.length - 1];
  const appendedMessageCount = nextMessages.length - previousMessages.length;

  if (nextLatestMessage?.role !== "assistant") {
    return false;
  }

  const latestChanged = nextLatestMessage.id !== previousLatestMessage?.id;
  const latestContinued =
    nextLatestMessage.id === previousLatestMessage?.id &&
    previousLatestMessage?.role === "assistant";

  if (latestChanged) {
    return !manualDetachActive && appendedMessageCount === 1;
  }

  if (
    latestContinued &&
    previousLatestMessage?.isStreaming === true &&
    nextLatestMessage.isStreaming === false
  ) {
    return (
      !manualDetachActive &&
      (autoScrollActive || isNearBottom || shouldMaintainStreamLock)
    );
  }

  // Keep the existing bottom-lock loop running, but don't restart it on every
  // streaming update for the same assistant message. Repeated restarts cause
  // visible scroll jitter when message height is still changing.
  if (latestContinued) {
    return (
      !manualDetachActive &&
      nextLatestMessage.isStreaming !== false &&
      !autoScrollActive &&
      (isNearBottom || shouldMaintainStreamLock)
    );
  }

  return false;
}

export function shouldStopAutoScrollOnUserScroll({
  autoScrollActive,
  programmaticScroll,
  movedUp,
  isAwayFromBottom,
  deltaScrollPx,
}: {
  isMobileViewport: boolean;
  autoScrollActive: boolean;
  programmaticScroll: boolean;
  movedUp: boolean;
  isAwayFromBottom: boolean;
  deltaScrollPx: number;
  scrollTop: number;
}): boolean {
  if (!autoScrollActive || programmaticScroll || !movedUp) {
    return false;
  }

  if (isAwayFromBottom) {
    return true;
  }

  return deltaScrollPx > 6;
}

export function shouldIgnoreUnexpectedTopJumpDuringBottomLock({
  scrollTop,
  clientHeight,
  scrollHeight,
  autoScrollActive,
  recentlyBottomLocked = false,
  userScrolledUp,
  manualDetachActive,
}: {
  scrollTop: number;
  clientHeight: number;
  scrollHeight: number;
  autoScrollActive: boolean;
  recentlyBottomLocked?: boolean;
  userScrolledUp: boolean;
  manualDetachActive: boolean;
}): boolean {
  return (
    (autoScrollActive || recentlyBottomLocked) &&
    !userScrolledUp &&
    !manualDetachActive &&
    scrollTop <= 1 &&
    scrollHeight > clientHeight + 1
  );
}

export function getUnexpectedTopJumpRecoveryUntilAfterUserIntent({
  recoverUntil,
  now,
}: {
  recoverUntil: number;
  now: number;
}): number {
  return now <= recoverUntil ? 0 : recoverUntil;
}

export function shouldAutoScrollAfterViewportChange({
  scroller,
  bottomBreathingRoomPx,
  userScrolledUp,
  autoScrollActive,
  isNearBottom,
}: {
  scroller?: ScrollerLike | null;
  bottomBreathingRoomPx: number;
  userScrolledUp: boolean;
  autoScrollActive: boolean;
  isNearBottom: boolean;
}): boolean {
  if (!scroller || userScrolledUp) {
    return false;
  }

  const hasScrollableOverflow =
    scroller.scrollHeight > scroller.clientHeight + bottomBreathingRoomPx;
  if (!hasScrollableOverflow) {
    return false;
  }

  return autoScrollActive || isNearBottom;
}

export function forceScrollerToPhysicalBottom({
  scroller,
  footer,
}: {
  scroller?: ScrollerLike | null;
  footer?: FooterLike | null;
}): void {
  footer?.scrollIntoView({ behavior: "auto", block: "end" });
  if (scroller) {
    scroller.scrollTop = scroller.scrollHeight;
  }
}

export function forceVirtuosoToBottom({
  virtuoso,
  scroller,
  footer,
}: {
  virtuoso?: VirtuosoLike | null;
  scroller?: ScrollerLike | null;
  footer?: FooterLike | null;
}): void {
  if (virtuoso?.scrollToIndex) {
    virtuoso.scrollToIndex({
      index: "LAST",
      align: "end",
      behavior: "auto",
    });
    return;
  }

  if (typeof virtuoso?.autoscrollToBottom === "function") {
    virtuoso.autoscrollToBottom();
    return;
  }

  if (virtuoso) {
    virtuoso.scrollTo({
      top: Number.MAX_SAFE_INTEGER,
      behavior: "auto",
    });
    return;
  }

  if (scroller) {
    scroller.scrollTop = scroller.scrollHeight;
    return;
  }

  forceScrollerToPhysicalBottom({ scroller, footer });
}

export function startVirtuosoScrollToBottom({
  virtuoso,
  scroller,
  footer,
  preferPhysicalBottom = false,
  intervalMs = 30,
  maxAttempts = 40,
  maxDurationMs,
  settleWindowMs,
  observeLayoutChanges = false,
  resizeObserverFactory,
  resizeObserverTarget,
  observeAfterSettleMs = 0,
  keepAliveWhile,
  shouldAbort,
  onAutoScroll,
  onInitialSettle,
  onComplete,
  resetBudgetOnLayoutChange = observeLayoutChanges,
}: StartVirtuosoScrollToBottomOptions): () => void {
  if (!virtuoso || !scroller) {
    forceVirtuosoToBottom({ virtuoso, scroller, footer });
    onComplete?.("settled");
    return () => undefined;
  }

  let attempts = 0;
  let lastKnownScrollHeight = scroller.scrollHeight;
  let lastHeightChangeAt = Date.now();
  let startedAt = Date.now();
  let finished = false;
  let resizeObserver: ResizeObserverLike | null = null;
  let keepAliveActive = false;
  let postSettleObserveUntil = 0;
  let initialSettleNotified = false;
  const notifyInitialSettle = () => {
    if (initialSettleNotified) return;
    initialSettleNotified = true;
    onInitialSettle?.();
  };
  const finish = (reason: "settled" | "aborted" | "max-attempts") => {
    if (finished) return;
    finished = true;
    clearInterval(timer);
    resizeObserver?.disconnect();
    resizeObserver = null;
    onComplete?.(reason);
  };
  const scroll = () => {
    onAutoScroll?.();
    if (preferPhysicalBottom && (footer || scroller)) {
      forceVirtuosoToBottom({ virtuoso, footer: virtuoso ? null : footer });
      if (scroller) {
        scroller.scrollTop = scroller.scrollHeight;
      }
      return;
    }
    if (typeof virtuoso.autoscrollToBottom === "function") {
      virtuoso.autoscrollToBottom();
      return;
    }
    forceVirtuosoToBottom({ virtuoso, footer });
  };

  scroll();

  // Minimum attempts before checking isAtBottom — Virtuoso may report
  // being at the "bottom" based on an initial height estimate that is
  // still being refined as it measures item heights.  Forcing a few
  // extra scrollTo calls gives it time to settle at the true bottom.
  const minAttemptsBeforeSettling = 5;
  const stableHeightWindowMs = settleWindowMs ?? Math.max(intervalMs * 4, 120);
  const maxScrollWindowMs =
    maxDurationMs ?? Math.max(intervalMs * maxAttempts, stableHeightWindowMs);
  const isAtKnownBottom = () =>
    scroller.scrollTop + scroller.clientHeight >= lastKnownScrollHeight - 1;
  const isUnexpectedTopJump = () =>
    postSettleObserveUntil > 0 &&
    scroller.scrollTop <= 1 &&
    scroller.scrollHeight > scroller.clientHeight + 1;
  const resetSettleBudget = () => {
    attempts = 0;
    lastKnownScrollHeight = scroller.scrollHeight;
    lastHeightChangeAt = Date.now();
    startedAt = Date.now();
  };
  const noteLayoutChange = () => {
    if (resetBudgetOnLayoutChange && !keepAliveActive) {
      resetSettleBudget();
      return;
    }

    lastKnownScrollHeight = scroller.scrollHeight;
    lastHeightChangeAt = Date.now();
  };

  if (observeLayoutChanges) {
    const createResizeObserver =
      resizeObserverFactory ??
      (typeof ResizeObserver !== "undefined"
        ? (callback: () => void): ResizeObserverLike => {
            const observer = new ResizeObserver(() => callback());
            return {
              observe: (target) => {
                if (target instanceof Element) {
                  observer.observe(target);
                }
              },
              disconnect: () => observer.disconnect(),
            };
          }
        : null);

    if (createResizeObserver) {
      resizeObserver = createResizeObserver(() => {
        if (finished) return;
        if (shouldAbort?.()) {
          finish("aborted");
          return;
        }

        if (postSettleObserveUntil > 0 && !isAtKnownBottom()) {
          if (isUnexpectedTopJump()) {
            noteLayoutChange();
            scroll();
            return;
          }

          finish("aborted");
          return;
        }

        noteLayoutChange();
        scroll();
      });
      resizeObserver.observe(resizeObserverTarget ?? scroller);
    }
  }

  const timer = setInterval(() => {
    if (shouldAbort?.()) {
      finish("aborted");
      return;
    }

    const shouldKeepAlive = keepAliveWhile?.() === true;
    if (shouldKeepAlive) {
      keepAliveActive = true;

      if (scroller.scrollHeight !== lastKnownScrollHeight) {
        lastKnownScrollHeight = scroller.scrollHeight;
        lastHeightChangeAt = Date.now();
        scroll();
        return;
      }

      const isAtBottom =
        scroller.scrollTop + scroller.clientHeight >= scroller.scrollHeight - 1;
      if (!isAtBottom) {
        scroll();
      }
      return;
    }

    if (keepAliveActive) {
      keepAliveActive = false;
      resetSettleBudget();
    }

    attempts += 1;

    const heightChanged = scroller.scrollHeight !== lastKnownScrollHeight;

    const isAtBottom =
      scroller.scrollTop + scroller.clientHeight >= scroller.scrollHeight - 1;

    if (postSettleObserveUntil > 0) {
      if (!isAtBottom) {
        if (isUnexpectedTopJump()) {
          scroll();
          return;
        }

        if (!heightChanged) {
          finish("aborted");
          return;
        }

        if (!isAtKnownBottom()) {
          finish("aborted");
          return;
        }

        noteLayoutChange();
        scroll();
        return;
      }

      if (heightChanged) {
        noteLayoutChange();
      }

      if (Date.now() < postSettleObserveUntil) {
        return;
      }

      finish("settled");
      return;
    }

    if (heightChanged) {
      noteLayoutChange();
    }

    const hasStableHeight =
      Date.now() - lastHeightChangeAt >= stableHeightWindowMs;
    const hasReachedAttemptLimit = attempts >= maxAttempts;
    const hasExceededScrollBudget = Date.now() - startedAt >= maxScrollWindowMs;

    if (
      (isAtBottom &&
        hasStableHeight &&
        attempts >= minAttemptsBeforeSettling) ||
      hasReachedAttemptLimit ||
      hasExceededScrollBudget
    ) {
      if (
        isAtBottom &&
        hasStableHeight &&
        attempts >= minAttemptsBeforeSettling &&
        observeLayoutChanges &&
        observeAfterSettleMs > 0
      ) {
        notifyInitialSettle();
        postSettleObserveUntil = Date.now() + observeAfterSettleMs;
        return;
      }

      if (
        isAtBottom &&
        hasStableHeight &&
        attempts >= minAttemptsBeforeSettling
      ) {
        notifyInitialSettle();
      }
      finish(
        hasExceededScrollBudget || hasReachedAttemptLimit
          ? "max-attempts"
          : "settled",
      );
      return;
    }

    scroll();
  }, intervalMs);

  return () => {
    finish("aborted");
  };
}
