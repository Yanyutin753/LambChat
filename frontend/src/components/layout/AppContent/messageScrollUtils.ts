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
  scrollIntoView: (args?: { behavior?: ScrollBehaviorMode }) => void;
}

interface StartVirtuosoScrollToBottomOptions {
  virtuoso?: VirtuosoLike | null;
  scroller?: ScrollerLike | null;
  footer?: FooterLike | null;
  intervalMs?: number;
  maxAttempts?: number;
}

interface ScrollMessageLike {
  id: string;
  role?: string;
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

export function startVirtuosoScrollToBottom({
  virtuoso,
  scroller,
  footer,
  intervalMs = 30,
  maxAttempts = 20,
}: StartVirtuosoScrollToBottomOptions): () => void {
  if (!virtuoso || !scroller) {
    footer?.scrollIntoView({ behavior: "auto" });
    return () => undefined;
  }

  let attempts = 0;
  const scroll = () => {
    virtuoso.scrollTo({
      top: Number.MAX_SAFE_INTEGER,
      behavior: "auto",
    });
  };

  scroll();

  // Minimum attempts before checking isAtBottom — Virtuoso may report
  // being at the "bottom" based on an initial height estimate that is
  // still being refined as it measures item heights.  Forcing a few
  // extra scrollTo calls gives it time to settle at the true bottom.
  const minAttemptsBeforeSettling = 5;

  const timer = setInterval(() => {
    attempts += 1;

    const isAtBottom =
      scroller.scrollTop + scroller.clientHeight >= scroller.scrollHeight - 1;

    if (
      (isAtBottom && attempts >= minAttemptsBeforeSettling) ||
      attempts >= maxAttempts
    ) {
      clearInterval(timer);
      return;
    }

    scroll();
  }, intervalMs);

  return () => clearInterval(timer);
}
