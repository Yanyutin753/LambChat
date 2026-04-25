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
  // Kept for compatibility with older callers. Settling must still require
  // the physical scroll bottom, otherwise the user can still drag lower.
  bottomOffsetPx?: number;
  keepAliveWhile?: () => boolean;
  shouldAbort?: () => boolean;
  onAutoScroll?: () => void;
  onComplete?: (reason: "settled" | "aborted" | "max-attempts") => void;
  resetBudgetOnLayoutChange?: boolean;
}

export interface ScrollMessageLike {
  id: string;
  role?: string;
}

export function getAtBottomThresholdPx(isMobileViewport: boolean): number {
  return isMobileViewport ? 120 : 4;
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
    return appendedMessageCount === 1;
  }

  // Keep the existing bottom-lock loop running, but don't restart it on every
  // streaming update for the same assistant message. Repeated restarts cause
  // visible scroll jitter when message height is still changing.
  if (latestContinued) {
    return (
      !manualDetachActive &&
      !autoScrollActive &&
      (isNearBottom || shouldMaintainStreamLock)
    );
  }

  return false;
}

export function shouldStopAutoScrollOnUserScroll({
  isMobileViewport,
  autoScrollActive,
  programmaticScroll,
  movedUp,
  isAwayFromBottom,
  deltaScrollPx,
  scrollTop,
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

  if (!isMobileViewport) {
    return false;
  }

  return deltaScrollPx > 6 && scrollTop >= 0;
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
  const pinScrollerToBottom = () => {
    if (scroller) {
      scroller.scrollTop = scroller.scrollHeight;
      return true;
    }
    return false;
  };

  if (virtuoso?.scrollToIndex) {
    virtuoso.scrollToIndex({
      index: "LAST",
      align: "end",
      behavior: "auto",
    });
    pinScrollerToBottom();
    return;
  }

  if (typeof virtuoso?.autoscrollToBottom === "function") {
    virtuoso.autoscrollToBottom();
    pinScrollerToBottom();
    return;
  }

  if (virtuoso) {
    virtuoso.scrollTo({
      top: Number.MAX_SAFE_INTEGER,
      behavior: "auto",
    });
    pinScrollerToBottom();
    return;
  }

  if (pinScrollerToBottom()) {
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
  keepAliveWhile,
  shouldAbort,
  onAutoScroll,
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
      forceScrollerToPhysicalBottom({ scroller, footer });
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

    if (scroller.scrollHeight !== lastKnownScrollHeight) {
      noteLayoutChange();
    }

    const isAtBottom =
      scroller.scrollTop + scroller.clientHeight >= scroller.scrollHeight - 1;
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
