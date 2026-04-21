type ScrollBehaviorMode = "auto" | "smooth";

interface VirtuosoLike {
  scrollTo: (args: { top: number; behavior: ScrollBehaviorMode }) => void;
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
  shouldAbort?: () => boolean;
  onAutoScroll?: () => void;
  onComplete?: (reason: "settled" | "aborted" | "max-attempts") => void;
}

interface ScrollMessageLike {
  id: string;
  role?: string;
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
}: {
  previousMessages: ScrollMessageLike[];
  nextMessages: ScrollMessageLike[];
  userScrolledUp: boolean;
  autoScrollActive: boolean;
  isNearBottom: boolean;
}): boolean {
  if (userScrolledUp || nextMessages.length === 0) {
    return false;
  }

  if (!autoScrollActive && !isNearBottom) {
    return false;
  }

  const previousLatestMessage = previousMessages[previousMessages.length - 1];
  const nextLatestMessage = nextMessages[nextMessages.length - 1];

  if (nextLatestMessage?.role !== "assistant") {
    return false;
  }

  const latestChanged = nextLatestMessage.id !== previousLatestMessage?.id;
  const latestContinued =
    nextLatestMessage.id === previousLatestMessage?.id &&
    previousLatestMessage?.role === "assistant";

  return latestChanged || latestContinued;
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

export function startVirtuosoScrollToBottom({
  virtuoso,
  scroller,
  footer,
  intervalMs = 30,
  maxAttempts = 40,
  maxDurationMs,
  settleWindowMs,
  observeLayoutChanges = false,
  resizeObserverFactory,
  resizeObserverTarget,
  shouldAbort,
  onAutoScroll,
  onComplete,
}: StartVirtuosoScrollToBottomOptions): () => void {
  if (!virtuoso || !scroller) {
    footer?.scrollIntoView({ behavior: "auto" });
    onComplete?.("settled");
    return () => undefined;
  }

  let attempts = 0;
  let lastKnownScrollHeight = scroller.scrollHeight;
  let lastHeightChangeAt = Date.now();
  let finished = false;
  let resizeObserver: ResizeObserverLike | null = null;
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
    virtuoso.scrollTo({
      top: Number.MAX_SAFE_INTEGER,
      behavior: "auto",
    });
    footer?.scrollIntoView({ behavior: "auto", block: "end" });
  };

  scroll();

  // Minimum attempts before checking isAtBottom — Virtuoso may report
  // being at the "bottom" based on an initial height estimate that is
  // still being refined as it measures item heights.  Forcing a few
  // extra scrollTo calls gives it time to settle at the true bottom.
  const minAttemptsBeforeSettling = 5;
  const stableHeightWindowMs = settleWindowMs ?? Math.max(intervalMs * 4, 120);
  const maxScrollWindowMs = maxDurationMs ?? intervalMs * maxAttempts;
  const startedAt = Date.now();

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

        lastKnownScrollHeight = scroller.scrollHeight;
        lastHeightChangeAt = Date.now();
        scroll();
      });
      resizeObserver.observe(resizeObserverTarget ?? scroller);
    }
  }

  const timer = setInterval(() => {
    attempts += 1;

    if (shouldAbort?.()) {
      finish("aborted");
      return;
    }

    if (scroller.scrollHeight !== lastKnownScrollHeight) {
      lastKnownScrollHeight = scroller.scrollHeight;
      lastHeightChangeAt = Date.now();
    }

    const isAtBottom =
      scroller.scrollTop + scroller.clientHeight >= scroller.scrollHeight - 1;
    const hasStableHeight =
      Date.now() - lastHeightChangeAt >= stableHeightWindowMs;
    const hasExceededScrollBudget = Date.now() - startedAt >= maxScrollWindowMs;

    if (
      (isAtBottom &&
        hasStableHeight &&
        attempts >= minAttemptsBeforeSettling) ||
      hasExceededScrollBudget
    ) {
      finish(hasExceededScrollBudget ? "max-attempts" : "settled");
      return;
    }

    scroll();
  }, intervalMs);

  return () => {
    finish("aborted");
  };
}
