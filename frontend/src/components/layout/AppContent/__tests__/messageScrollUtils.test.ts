import {
  forceScrollerToPhysicalBottom,
  forceVirtuosoToBottom,
  getUnexpectedTopJumpRecoveryUntilAfterUserIntent,
  getAutoScrollResumeThresholdPx,
  getAtBottomThresholdPx,
  getAwayFromBottomThresholdPx,
  getScrollToBottomTimingOptions,
  getMessageListFooterSpacerClass,
  getInitialBottomItemLocation,
  getMessageListSessionKey,
  hasNewOutgoingMessage,
  shouldIgnoreUnexpectedTopJumpDuringBottomLock,
  shouldStopAutoScrollOnUserScroll,
  shouldAutoScrollForMessageUpdate,
  shouldAutoScrollAfterViewportChange,
  startVirtuosoScrollToBottom,
} from "../messageScrollUtils.ts";

test("keeps asking Virtuoso to scroll until the scroller reaches the bottom", async () => {
  const scrollCalls: Array<{ top: number; behavior: string }> = [];
  const scroller = {
    scrollTop: 0,
    clientHeight: 100,
    scrollHeight: 500,
  };
  const virtuoso = {
    scrollTo: (args: { top: number; behavior: string }) => {
      scrollCalls.push(args);
      if (scrollCalls.length >= 3) {
        scroller.scrollTop = scroller.scrollHeight - scroller.clientHeight;
      }
    },
  };

  const stop = startVirtuosoScrollToBottom({
    virtuoso,
    scroller,
    intervalMs: 1,
    maxAttempts: 5,
  });

  await new Promise((resolve) => setTimeout(resolve, 20));
  stop();

  expect(scrollCalls.length >= 2).toBeTruthy();
  expect(scrollCalls[0]).toEqual({
    top: Number.MAX_SAFE_INTEGER,
    behavior: "auto",
  });
});

test("forces the physical scroller during a preferred bottom lock even when Virtuoso is mounted", async () => {
  const scroller = {
    scrollTop: 0,
    clientHeight: 100,
    scrollHeight: 500,
  };
  const virtuoso = {
    scrollTo: () => {
      scroller.scrollTop = 0;
    },
  };

  const stop = startVirtuosoScrollToBottom({
    virtuoso,
    scroller,
    preferPhysicalBottom: true,
    intervalMs: 1,
    maxAttempts: 1,
  });

  await new Promise((resolve) => setTimeout(resolve, 5));
  stop();

  expect(scroller.scrollTop).toBe(scroller.scrollHeight);
});

test("initializes history at the bottom edge of the latest message", () => {
  expect(getInitialBottomItemLocation(3)).toEqual({
    index: 2,
    align: "end",
  });

  expect(getInitialBottomItemLocation(0)).toBe(undefined);
});

test("changes the message list key when switching sessions", () => {
  expect(getMessageListSessionKey("session-a")).toBe("session-a");
  expect(getMessageListSessionKey("session-b")).toBe("session-b");
  expect(getMessageListSessionKey("session-a")).not.toBe(
    getMessageListSessionKey("session-b"),
  );
  expect(getMessageListSessionKey(null)).toBe("__new_session__");
});

test("uses a much tighter bottom threshold on desktop than on mobile", () => {
  expect(getAtBottomThresholdPx(false)).toBe(4);
  expect(getAtBottomThresholdPx(true)).toBe(120);
  expect(getAutoScrollResumeThresholdPx(false, 16)).toBe(48);
  expect(getAutoScrollResumeThresholdPx(true, 96)).toBe(120);
  expect(getAwayFromBottomThresholdPx(false, 16)).toBe(16);
  expect(getAwayFromBottomThresholdPx(true, 96)).toBe(96);
});

test("keeps the mobile footer spacer compact so history loads can settle near the latest message", () => {
  expect(getMessageListFooterSpacerClass(true)).toBe(
    "h-[calc(1.5rem+env(safe-area-inset-bottom))]",
  );
  expect(getMessageListFooterSpacerClass(false)).toBe("h-8");
});

test("falls back to the footer sentinel when Virtuoso handles are unavailable", () => {
  let called = false;
  const footer = {
    scrollIntoView: (args?: { behavior?: "auto" | "smooth" }) => {
      called = args?.behavior === "auto";
    },
  };

  const stop = startVirtuosoScrollToBottom({
    footer,
  });
  stop();

  expect(called).toBe(true);
});

test("forwards scroller to the physical-bottom fallback when Virtuoso is temporarily unavailable", () => {
  const scroller = {
    scrollTop: 0,
    clientHeight: 100,
    scrollHeight: 640,
  };
  const footer = {
    scrollIntoView: (args?: {
      behavior?: "auto" | "smooth";
      block?: ScrollLogicalPosition;
    }) => {
      return args;
    },
  };

  const stop = startVirtuosoScrollToBottom({
    virtuoso: null,
    scroller,
    footer,
  });
  stop();

  expect(scroller.scrollTop).toBe(scroller.scrollHeight);
});

test("forces the physical bottom by scrolling the footer sentinel into view", () => {
  let footerArgs:
    | { behavior?: "auto" | "smooth"; block?: ScrollLogicalPosition }
    | undefined;
  const scroller = {
    scrollTop: 0,
    clientHeight: 100,
    scrollHeight: 640,
  };
  const footer = {
    scrollIntoView: (args?: {
      behavior?: "auto" | "smooth";
      block?: ScrollLogicalPosition;
    }) => {
      footerArgs = args;
      scroller.scrollTop = scroller.scrollHeight;
    },
  };

  forceScrollerToPhysicalBottom({ scroller, footer });

  expect(footerArgs).toEqual({
    behavior: "auto",
    block: "end",
  });
  expect(scroller.scrollTop).toBe(scroller.scrollHeight);
});

test("keeps Virtuoso synced while physically pinning the scroller during a bottom lock", async () => {
  let scrollToIndexCalls = 0;
  let footerCalls = 0;
  const scroller = {
    scrollTop: 0,
    clientHeight: 100,
    scrollHeight: 640,
  };
  const footer = {
    scrollIntoView: () => {
      footerCalls += 1;
      scroller.scrollTop = scroller.scrollHeight;
    },
  };
  const virtuoso = {
    scrollTo: () => undefined,
    scrollToIndex: () => {
      scrollToIndexCalls += 1;
    },
  };

  const stop = startVirtuosoScrollToBottom({
    virtuoso,
    scroller,
    footer,
    preferPhysicalBottom: true,
    intervalMs: 1,
    maxAttempts: 5,
  });

  await new Promise((resolve) => setTimeout(resolve, 20));
  stop();

  expect(scrollToIndexCalls > 0).toBeTruthy();
  expect(footerCalls).toBe(0);
  expect(scroller.scrollTop).toBe(scroller.scrollHeight);
});

test("treats a top jump right after bottom-locking as recoverable", () => {
  expect(
    shouldIgnoreUnexpectedTopJumpDuringBottomLock({
      scrollTop: 0,
      clientHeight: 600,
      scrollHeight: 2400,
      autoScrollActive: false,
      recentlyBottomLocked: true,
      userScrolledUp: false,
      manualDetachActive: false,
    }),
  ).toBe(true);
});

test("does not recover a top jump after the user intentionally detached", () => {
  expect(
    shouldIgnoreUnexpectedTopJumpDuringBottomLock({
      scrollTop: 0,
      clientHeight: 600,
      scrollHeight: 2400,
      autoScrollActive: false,
      recentlyBottomLocked: true,
      userScrolledUp: true,
      manualDetachActive: false,
    }),
  ).toBe(false);
});

test("clears the unexpected top jump recovery window on user intent", () => {
  expect(
    getUnexpectedTopJumpRecoveryUntilAfterUserIntent({
      recoverUntil: 2000,
      now: 1000,
    }),
  ).toBe(0);

  expect(
    getUnexpectedTopJumpRecoveryUntilAfterUserIntent({
      recoverUntil: 1000,
      now: 2000,
    }),
  ).toBe(1000);
});

test("forces the list to the last item when Virtuoso supports scrollToIndex", () => {
  let scrollToIndexArgs:
    | { index: "LAST" | number; align?: string; behavior?: string }
    | undefined;
  const scroller = {
    scrollTop: 0,
    clientHeight: 100,
    scrollHeight: 640,
  };
  const virtuoso = {
    scrollTo: () => undefined,
    scrollToIndex: (args: {
      index: "LAST" | number;
      align?: "center" | "end" | "start";
      behavior?: "auto" | "smooth";
    }) => {
      scrollToIndexArgs = args;
    },
  };

  forceVirtuosoToBottom({ virtuoso, scroller });

  expect(scrollToIndexArgs).toEqual({
    index: "LAST",
    align: "end",
    behavior: "auto",
  });
  expect(scroller.scrollTop).toBe(0);
});

test("prefers Virtuoso scrolling without nudging the footer sentinel when handles are available", async () => {
  let footerScrolls = 0;
  let virtuosoScrolls = 0;
  const virtuoso = {
    scrollTo: () => {
      virtuosoScrolls += 1;
    },
  };
  const scroller = {
    scrollTop: 0,
    clientHeight: 100,
    scrollHeight: 500,
  };
  const footer = {
    scrollIntoView: () => {
      footerScrolls += 1;
      scroller.scrollTop = scroller.scrollHeight - scroller.clientHeight;
    },
  };

  startVirtuosoScrollToBottom({
    virtuoso,
    scroller,
    footer,
    intervalMs: 1,
    maxDurationMs: 20,
  });

  await new Promise((resolve) => setTimeout(resolve, 5));

  expect(virtuosoScrolls > 0).toBeTruthy();
  expect(footerScrolls).toBe(0);
});

test("prefers Virtuoso autoscrollToBottom when the handle supports it", async () => {
  let autoScrollCalls = 0;
  let scrollToCalls = 0;
  const scroller = {
    scrollTop: 0,
    clientHeight: 100,
    scrollHeight: 500,
  };
  const virtuoso = {
    autoscrollToBottom: () => {
      autoScrollCalls += 1;
      scroller.scrollTop = scroller.scrollHeight - scroller.clientHeight;
    },
    scrollTo: () => {
      scrollToCalls += 1;
    },
  };

  startVirtuosoScrollToBottom({
    virtuoso,
    scroller,
    intervalMs: 1,
    maxAttempts: 5,
  });

  await new Promise((resolve) => setTimeout(resolve, 20));

  expect(autoScrollCalls > 0).toBeTruthy();
  expect(scrollToCalls).toBe(0);
});

test("does not settle early just because the scroller is within the breathing room", async () => {
  let completionReason: "settled" | "aborted" | "max-attempts" | null = null;
  const virtuoso = {
    scrollTo: () => undefined,
  };
  const scroller = {
    scrollTop: 460,
    clientHeight: 100,
    scrollHeight: 600,
  };

  startVirtuosoScrollToBottom({
    virtuoso,
    scroller,
    intervalMs: 5,
    maxDurationMs: 140,
    bottomOffsetPx: 40,
    onComplete: (reason) => {
      completionReason = reason;
    },
  });

  await new Promise((resolve) => setTimeout(resolve, 130));

  expect(completionReason).not.toBe("settled");
});

test("waits for the configured stable height window before settling", async () => {
  let completionReason: "settled" | "aborted" | "max-attempts" | null = null;
  const virtuoso = {
    scrollTo: () => undefined,
  };
  const scroller = {
    scrollTop: 400,
    clientHeight: 100,
    scrollHeight: 500,
  };

  startVirtuosoScrollToBottom({
    virtuoso,
    scroller,
    intervalMs: 5,
    maxAttempts: 80,
    maxDurationMs: 400,
    settleWindowMs: 220,
    onComplete: (reason) => {
      completionReason = reason;
    },
  });

  await new Promise((resolve) => setTimeout(resolve, 160));
  expect(completionReason).toBe(null);

  await new Promise((resolve) => setTimeout(resolve, 100));
  expect(completionReason).toBe("settled");
});

test("honors the configured maxAttempts instead of retrying until the time budget expires", async () => {
  let completionReason: "settled" | "aborted" | "max-attempts" | null = null;
  let scrollCalls = 0;
  const virtuoso = {
    scrollTo: () => {
      scrollCalls += 1;
    },
  };
  const scroller = {
    scrollTop: 0,
    clientHeight: 100,
    scrollHeight: 500,
  };

  startVirtuosoScrollToBottom({
    virtuoso,
    scroller,
    intervalMs: 5,
    maxAttempts: 3,
    maxDurationMs: 500,
    onComplete: (reason) => {
      completionReason = reason;
    },
  });

  await new Promise((resolve) => setTimeout(resolve, 80));

  expect(completionReason).toBe("max-attempts");
  expect(scrollCalls).toBe(3);
});

test("keeps bottom locked when observed layout changes", async () => {
  let observedTarget: unknown = null;
  let resizeCallback: () => void = () => {
    throw new Error("resize observer was not registered");
  };
  let disconnected = false;
  const scroller = {
    scrollTop: 400,
    clientHeight: 100,
    scrollHeight: 500,
  };
  const virtuoso = {
    scrollTo: () => {
      scroller.scrollTop = scroller.scrollHeight - scroller.clientHeight;
    },
  };

  const stop = startVirtuosoScrollToBottom({
    virtuoso,
    scroller,
    intervalMs: 20,
    maxDurationMs: 400,
    settleWindowMs: 160,
    observeLayoutChanges: true,
    resizeObserverFactory: (callback) => {
      resizeCallback = callback;
      return {
        observe: (target) => {
          observedTarget = target;
        },
        disconnect: () => {
          disconnected = true;
        },
      };
    },
  });

  await new Promise((resolve) => setTimeout(resolve, 30));
  expect(observedTarget).toBe(scroller);

  scroller.scrollHeight = 700;
  resizeCallback();

  expect(scroller.scrollTop).toBe(600);

  stop();
  expect(disconnected).toBe(true);
});

test("keeps the resize observer alive past the normal time budget while a streaming lock is active", async () => {
  let resizeCallback: () => void = () => {
    throw new Error("resize observer was not registered");
  };
  let disconnected = false;
  let completionReason: "settled" | "aborted" | "max-attempts" | null = null;
  let keepStreamingLock = true;
  const scroller = {
    scrollTop: 400,
    clientHeight: 100,
    scrollHeight: 500,
  };
  const virtuoso = {
    scrollTo: () => {
      scroller.scrollTop = scroller.scrollHeight - scroller.clientHeight;
    },
  };

  startVirtuosoScrollToBottom({
    virtuoso,
    scroller,
    intervalMs: 5,
    maxAttempts: 8,
    maxDurationMs: 60,
    settleWindowMs: 10,
    observeLayoutChanges: true,
    keepAliveWhile: () => keepStreamingLock,
    resizeObserverFactory: (callback) => {
      resizeCallback = callback;
      return {
        observe: () => undefined,
        disconnect: () => {
          disconnected = true;
        },
      };
    },
    onComplete: (reason) => {
      completionReason = reason;
    },
  });

  await new Promise((resolve) => setTimeout(resolve, 60));
  expect(completionReason).toBe(null);
  expect(disconnected).toBe(false);

  scroller.scrollHeight = 700;
  resizeCallback();
  expect(scroller.scrollTop).toBe(600);

  keepStreamingLock = false;

  await new Promise((resolve) => setTimeout(resolve, 40));
  expect(completionReason).toBe("settled");
  expect(disconnected).toBe(true);
});

test("extends the settle window when observed layout changes keep arriving during history finalize", async () => {
  let resizeCallback: () => void = () => {
    throw new Error("resize observer was not registered");
  };
  let completionReason: "settled" | "aborted" | "max-attempts" | null = null;
  const scroller = {
    scrollTop: 400,
    clientHeight: 100,
    scrollHeight: 500,
  };
  const virtuoso = {
    scrollTo: () => {
      scroller.scrollTop = scroller.scrollHeight - scroller.clientHeight;
    },
  };

  startVirtuosoScrollToBottom({
    virtuoso,
    scroller,
    intervalMs: 5,
    maxAttempts: 80,
    maxDurationMs: 40,
    settleWindowMs: 30,
    observeLayoutChanges: true,
    onComplete: (reason) => {
      completionReason = reason;
    },
    resizeObserverFactory: (callback) => {
      resizeCallback = callback;
      return {
        observe: () => undefined,
        disconnect: () => undefined,
      };
    },
  });

  await new Promise((resolve) => setTimeout(resolve, 25));
  scroller.scrollHeight = 700;
  resizeCallback();

  await new Promise((resolve) => setTimeout(resolve, 25));
  scroller.scrollHeight = 900;
  resizeCallback();

  await new Promise((resolve) => setTimeout(resolve, 10));
  expect(completionReason).toBe(null);

  await new Promise((resolve) => setTimeout(resolve, 40));
  expect(completionReason).toBe("settled");
  expect(scroller.scrollTop).toBe(800);
});

test("keeps history bottom lock alive for late layout shifts after the first settle", async () => {
  let resizeCallback: () => void = () => {
    throw new Error("resize observer was not registered");
  };
  let completionReason: "settled" | "aborted" | "max-attempts" | null = null;
  const scroller = {
    scrollTop: 400,
    clientHeight: 100,
    scrollHeight: 500,
  };
  const virtuoso = {
    scrollTo: () => {
      scroller.scrollTop = scroller.scrollHeight - scroller.clientHeight;
    },
  };

  startVirtuosoScrollToBottom({
    virtuoso,
    scroller,
    intervalMs: 5,
    maxAttempts: 80,
    maxDurationMs: 60,
    settleWindowMs: 10,
    observeLayoutChanges: true,
    observeAfterSettleMs: 100,
    onComplete: (reason) => {
      completionReason = reason;
    },
    resizeObserverFactory: (callback) => {
      resizeCallback = callback;
      return {
        observe: () => undefined,
        disconnect: () => undefined,
      };
    },
  });

  await new Promise((resolve) => setTimeout(resolve, 45));
  expect(completionReason).toBe(null);

  scroller.scrollHeight = 900;
  resizeCallback();

  expect(scroller.scrollTop).toBe(800);

  await new Promise((resolve) => setTimeout(resolve, 130));
  expect(completionReason).toBe("settled");
});

test("reports the first stable bottom before the post-settle observation window finishes", async () => {
  const scroller = {
    scrollTop: 400,
    clientHeight: 200,
    scrollHeight: 600,
  };
  let initialSettleCalls = 0;
  let completeCalls = 0;
  const virtuoso = {
    scrollTo: () => {
      scroller.scrollTop = scroller.scrollHeight - scroller.clientHeight;
    },
  };

  const stop = startVirtuosoScrollToBottom({
    virtuoso,
    scroller,
    intervalMs: 5,
    maxAttempts: 20,
    settleWindowMs: 15,
    observeLayoutChanges: true,
    observeAfterSettleMs: 100,
    onInitialSettle: () => {
      initialSettleCalls += 1;
    },
    onComplete: () => {
      completeCalls += 1;
    },
  });

  await new Promise((resolve) => setTimeout(resolve, 45));

  expect(initialSettleCalls).toBe(1);
  expect(completeCalls).toBe(0);

  stop();
});

test("does not keep extending post-settle observation on repeated layout changes", async () => {
  let resizeCallback: () => void = () => {
    throw new Error("resize observer was not registered");
  };
  let completionReason: "settled" | "aborted" | "max-attempts" | null = null;
  const scroller = {
    scrollTop: 400,
    clientHeight: 100,
    scrollHeight: 500,
  };
  const virtuoso = {
    scrollTo: () => {
      scroller.scrollTop = scroller.scrollHeight - scroller.clientHeight;
    },
  };

  startVirtuosoScrollToBottom({
    virtuoso,
    scroller,
    intervalMs: 5,
    maxAttempts: 80,
    maxDurationMs: 60,
    settleWindowMs: 10,
    observeLayoutChanges: true,
    observeAfterSettleMs: 50,
    onComplete: (reason) => {
      completionReason = reason;
    },
    resizeObserverFactory: (callback) => {
      resizeCallback = callback;
      return {
        observe: () => undefined,
        disconnect: () => undefined,
      };
    },
  });

  await new Promise((resolve) => setTimeout(resolve, 35));
  expect(completionReason).toBe(null);

  for (let i = 0; i < 3; i += 1) {
    scroller.scrollHeight += 100;
    resizeCallback();
    await new Promise((resolve) => setTimeout(resolve, 25));
  }

  expect(completionReason).toBe("settled");

  scroller.scrollTop = 123;
  scroller.scrollHeight += 100;
  resizeCallback();
  expect(scroller.scrollTop).toBe(123);
});

test("keeps default bottom lock alive briefly for post-stream layout shifts", async () => {
  let resizeCallback: () => void = () => {
    throw new Error("resize observer was not registered");
  };
  let completionReason: "settled" | "aborted" | "max-attempts" | null = null;
  const scroller = {
    scrollTop: 400,
    clientHeight: 100,
    scrollHeight: 500,
  };
  const virtuoso = {
    scrollTo: () => {
      scroller.scrollTop = scroller.scrollHeight - scroller.clientHeight;
    },
  };
  const timing = getScrollToBottomTimingOptions({
    isMobileViewport: false,
    mode: "default",
  });

  startVirtuosoScrollToBottom({
    virtuoso,
    scroller,
    intervalMs: 5,
    maxAttempts: 80,
    maxDurationMs: 60,
    settleWindowMs: 10,
    observeLayoutChanges: true,
    observeAfterSettleMs: timing.observeAfterSettleMs,
    onComplete: (reason) => {
      completionReason = reason;
    },
    resizeObserverFactory: (callback) => {
      resizeCallback = callback;
      return {
        observe: () => undefined,
        disconnect: () => undefined,
      };
    },
  });

  await new Promise((resolve) => setTimeout(resolve, 45));
  expect(completionReason).toBe(null);

  scroller.scrollHeight = 900;
  resizeCallback();

  expect(scroller.scrollTop).toBe(800);
  expect(completionReason).toBe(null);
});

test("recovers an unexpected top jump during the post-stream bottom lock", async () => {
  let completionReason: "settled" | "aborted" | "max-attempts" | null = null;
  const scroller = {
    scrollTop: 400,
    clientHeight: 100,
    scrollHeight: 500,
  };
  const virtuoso = {
    scrollTo: () => {
      scroller.scrollTop = scroller.scrollHeight - scroller.clientHeight;
    },
  };

  startVirtuosoScrollToBottom({
    virtuoso,
    scroller,
    intervalMs: 5,
    maxAttempts: 80,
    maxDurationMs: 60,
    settleWindowMs: 10,
    observeLayoutChanges: true,
    observeAfterSettleMs: 100,
    onComplete: (reason) => {
      completionReason = reason;
    },
  });

  await new Promise((resolve) => setTimeout(resolve, 45));
  expect(completionReason).toBe(null);

  scroller.scrollTop = 0;
  await new Promise((resolve) => setTimeout(resolve, 15));

  expect(scroller.scrollTop).toBe(400);
  expect(completionReason).toBe(null);
});

test("does not pull back to bottom after the user leaves bottom during history settle observation", async () => {
  let resizeCallback: () => void = () => {
    throw new Error("resize observer was not registered");
  };
  let completionReason: "settled" | "aborted" | "max-attempts" | null = null;
  const scroller = {
    scrollTop: 400,
    clientHeight: 100,
    scrollHeight: 500,
  };
  const virtuoso = {
    scrollTo: () => {
      scroller.scrollTop = scroller.scrollHeight - scroller.clientHeight;
    },
  };

  startVirtuosoScrollToBottom({
    virtuoso,
    scroller,
    intervalMs: 5,
    maxAttempts: 80,
    maxDurationMs: 60,
    settleWindowMs: 10,
    observeLayoutChanges: true,
    observeAfterSettleMs: 100,
    onComplete: (reason) => {
      completionReason = reason;
    },
    resizeObserverFactory: (callback) => {
      resizeCallback = callback;
      return {
        observe: () => undefined,
        disconnect: () => undefined,
      };
    },
  });

  await new Promise((resolve) => setTimeout(resolve, 45));
  expect(completionReason).toBe(null);

  scroller.scrollTop = 360;
  scroller.scrollHeight = 900;
  resizeCallback();

  expect(scroller.scrollTop).toBe(360);
  expect(completionReason).toBe("aborted");
});

test("does not auto-scroll on viewport changes when the list is not scrollable", () => {
  expect(
    shouldAutoScrollAfterViewportChange({
      scroller: {
        scrollTop: 0,
        clientHeight: 520,
        scrollHeight: 540,
      },
      bottomBreathingRoomPx: 96,
      userScrolledUp: false,
      autoScrollActive: false,
      isNearBottom: true,
    }),
  ).toBe(false);
});

test("auto-scrolls on viewport changes only when a scrollable list is still bottom-anchored", () => {
  expect(
    shouldAutoScrollAfterViewportChange({
      scroller: {
        scrollTop: 800,
        clientHeight: 520,
        scrollHeight: 1600,
      },
      bottomBreathingRoomPx: 96,
      userScrolledUp: false,
      autoScrollActive: false,
      isNearBottom: true,
    }),
  ).toBe(true);

  expect(
    shouldAutoScrollAfterViewportChange({
      scroller: {
        scrollTop: 800,
        clientHeight: 520,
        scrollHeight: 1600,
      },
      bottomBreathingRoomPx: 96,
      userScrolledUp: true,
      autoScrollActive: false,
      isNearBottom: true,
    }),
  ).toBe(false);
});

test("detects when the local send path appends a user message and placeholder reply", () => {
  const hasOutgoingMessage = hasNewOutgoingMessage(
    [{ id: "1", role: "assistant" }],
    [
      { id: "1", role: "assistant" },
      { id: "2", role: "user" },
      { id: "3", role: "assistant" },
    ],
  );

  expect(hasOutgoingMessage).toBe(true);
});

test("does not treat assistant-only streaming updates or bulk history loads as local sends", () => {
  expect(
    hasNewOutgoingMessage(
      [{ id: "1", role: "user" }],
      [
        { id: "1", role: "user" },
        { id: "2", role: "assistant" },
      ],
    ),
  ).toBe(false);

  expect(
    hasNewOutgoingMessage(
      [],
      [
        { id: "1", role: "user" },
        { id: "2", role: "assistant" },
        { id: "3", role: "user" },
      ],
    ),
  ).toBe(false);
});

test("does not auto-scroll while history loading is still in progress", () => {
  expect(
    shouldAutoScrollForMessageUpdate({
      previousMessages: [],
      nextMessages: [
        { id: "1", role: "user" },
        { id: "2", role: "assistant" },
        { id: "3", role: "user" },
        { id: "4", role: "assistant" },
      ],
      userScrolledUp: false,
      autoScrollActive: false,
      isNearBottom: true,
      isLoadingHistory: true,
    }),
  ).toBe(false);
});

test("does not auto-scroll non-assistant bulk history updates just because the list grew", () => {
  expect(
    shouldAutoScrollForMessageUpdate({
      previousMessages: [{ id: "1", role: "user" }],
      nextMessages: [
        { id: "1", role: "user" },
        { id: "2", role: "assistant" },
        { id: "3", role: "user" },
      ],
      userScrolledUp: false,
      autoScrollActive: false,
      isNearBottom: false,
    }),
  ).toBe(false);
});

test("does not auto-scroll when multiple messages are appended at once", () => {
  expect(
    shouldAutoScrollForMessageUpdate({
      previousMessages: [{ id: "1", role: "user" }],
      nextMessages: [
        { id: "1", role: "user" },
        { id: "2", role: "assistant" },
        { id: "3", role: "assistant" },
      ],
      userScrolledUp: false,
      autoScrollActive: false,
      isNearBottom: true,
      isLoadingHistory: false,
    }),
  ).toBe(false);
});

test("treats an early upward mobile user scroll during active follow as an immediate detach", () => {
  expect(
    shouldStopAutoScrollOnUserScroll({
      isMobileViewport: true,
      autoScrollActive: true,
      programmaticScroll: false,
      movedUp: true,
      isAwayFromBottom: false,
      deltaScrollPx: 18,
      scrollTop: 260,
    }),
  ).toBe(true);
});

test("treats an early upward mobile user scroll as a detach even in short transcripts", () => {
  expect(
    shouldStopAutoScrollOnUserScroll({
      isMobileViewport: true,
      autoScrollActive: true,
      programmaticScroll: false,
      movedUp: true,
      isAwayFromBottom: false,
      deltaScrollPx: 12,
      scrollTop: 80,
    }),
  ).toBe(true);
});

test("does not stop auto-scroll for programmatic or tiny upward adjustments", () => {
  expect(
    shouldStopAutoScrollOnUserScroll({
      isMobileViewport: true,
      autoScrollActive: true,
      programmaticScroll: true,
      movedUp: true,
      isAwayFromBottom: true,
      deltaScrollPx: 40,
      scrollTop: 260,
    }),
  ).toBe(false);

  expect(
    shouldStopAutoScrollOnUserScroll({
      isMobileViewport: true,
      autoScrollActive: true,
      programmaticScroll: false,
      movedUp: true,
      isAwayFromBottom: false,
      deltaScrollPx: 1,
      scrollTop: 260,
    }),
  ).toBe(false);
});

test("ignores an unexpected top jump while the bottom lock is still active", () => {
  expect(
    shouldIgnoreUnexpectedTopJumpDuringBottomLock({
      scrollTop: 0,
      clientHeight: 100,
      scrollHeight: 500,
      autoScrollActive: true,
      userScrolledUp: false,
      manualDetachActive: false,
    }),
  ).toBe(true);

  expect(
    shouldIgnoreUnexpectedTopJumpDuringBottomLock({
      scrollTop: 0,
      clientHeight: 100,
      scrollHeight: 500,
      autoScrollActive: true,
      userScrolledUp: true,
      manualDetachActive: false,
    }),
  ).toBe(false);
});

test("treats that same early upward scroll as a detach on desktop too", () => {
  expect(
    shouldStopAutoScrollOnUserScroll({
      isMobileViewport: false,
      autoScrollActive: true,
      programmaticScroll: false,
      movedUp: true,
      isAwayFromBottom: false,
      deltaScrollPx: 18,
      scrollTop: 260,
    }),
  ).toBe(true);
});

test("auto-scrolls appended assistant messages only while the view is bottom-anchored", () => {
  const previousMessages = [{ id: "1", role: "user" }];
  const nextMessages = [
    { id: "1", role: "user" },
    { id: "2", role: "assistant" },
  ];

  expect(
    shouldAutoScrollForMessageUpdate({
      previousMessages,
      nextMessages,
      userScrolledUp: false,
      autoScrollActive: false,
      isNearBottom: true,
    }),
  ).toBe(true);

  expect(
    shouldAutoScrollForMessageUpdate({
      previousMessages,
      nextMessages,
      userScrolledUp: true,
      autoScrollActive: false,
      isNearBottom: false,
    }),
  ).toBe(false);
});

test("starts a bottom-lock run when a streaming assistant message continues near the bottom", () => {
  const previousMessages = [
    { id: "1", role: "user" },
    { id: "2", role: "assistant" },
  ];
  const nextMessages = [
    { id: "1", role: "user" },
    { id: "2", role: "assistant" },
  ];

  expect(
    shouldAutoScrollForMessageUpdate({
      previousMessages,
      nextMessages,
      userScrolledUp: false,
      autoScrollActive: false,
      isNearBottom: true,
      shouldMaintainStreamLock: false,
    }),
  ).toBe(true);
});

test("resumes bottom-lock for a streaming assistant update while the stream lock is still active", () => {
  const previousMessages = [
    { id: "1", role: "user" },
    { id: "2", role: "assistant" },
  ];
  const nextMessages = [
    { id: "1", role: "user" },
    { id: "2", role: "assistant" },
  ];

  expect(
    shouldAutoScrollForMessageUpdate({
      previousMessages,
      nextMessages,
      userScrolledUp: false,
      autoScrollActive: false,
      isNearBottom: false,
      shouldMaintainStreamLock: true,
    }),
  ).toBe(true);
});

test("does not restart bottom-lock while a streaming assistant update is already being followed", () => {
  const previousMessages = [
    { id: "1", role: "user" },
    { id: "2", role: "assistant" },
  ];
  const nextMessages = [
    { id: "1", role: "user" },
    { id: "2", role: "assistant" },
  ];

  expect(
    shouldAutoScrollForMessageUpdate({
      previousMessages,
      nextMessages,
      userScrolledUp: false,
      autoScrollActive: true,
      isNearBottom: false,
      shouldMaintainStreamLock: true,
    }),
  ).toBe(false);
});

test("does not allow detached mobile streaming to restart bottom-lock automatically", () => {
  const previousMessages = [
    { id: "1", role: "user" },
    { id: "2", role: "assistant" },
  ];
  const nextMessages = [
    { id: "1", role: "user" },
    { id: "2", role: "assistant" },
  ];

  expect(
    shouldAutoScrollForMessageUpdate({
      previousMessages,
      nextMessages,
      userScrolledUp: false,
      autoScrollActive: false,
      isNearBottom: false,
      shouldMaintainStreamLock: true,
      manualDetachActive: true,
    }),
  ).toBe(false);
});

test("does not auto-scroll a newly appended assistant message while detached", () => {
  const previousMessages = [{ id: "1", role: "user" }];
  const nextMessages = [
    { id: "1", role: "user" },
    { id: "2", role: "assistant" },
  ];

  expect(
    shouldAutoScrollForMessageUpdate({
      previousMessages,
      nextMessages,
      userScrolledUp: false,
      autoScrollActive: false,
      isNearBottom: true,
      manualDetachActive: true,
    }),
  ).toBe(false);
});

test("does not resume auto-scroll after stream lock is released when the view is no longer near bottom", () => {
  const previousMessages = [
    { id: "1", role: "user" },
    { id: "2", role: "assistant" },
  ];
  const nextMessages = [
    { id: "1", role: "user" },
    { id: "2", role: "assistant" },
  ];

  expect(
    shouldAutoScrollForMessageUpdate({
      previousMessages,
      nextMessages,
      userScrolledUp: false,
      autoScrollActive: false,
      isNearBottom: false,
      shouldMaintainStreamLock: false,
    }),
  ).toBe(false);
});
