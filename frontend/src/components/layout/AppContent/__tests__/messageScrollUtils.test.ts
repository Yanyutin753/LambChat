import test from "node:test";
import assert from "node:assert/strict";
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

  assert.ok(scrollCalls.length >= 2);
  assert.deepEqual(scrollCalls[0], {
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

  assert.equal(scroller.scrollTop, scroller.scrollHeight);
});

test("initializes history at the bottom edge of the latest message", () => {
  assert.deepEqual(getInitialBottomItemLocation(3), {
    index: 2,
    align: "end",
  });

  assert.equal(getInitialBottomItemLocation(0), undefined);
});

test("changes the message list key when switching sessions", () => {
  assert.equal(getMessageListSessionKey("session-a"), "session-a");
  assert.equal(getMessageListSessionKey("session-b"), "session-b");
  assert.notEqual(
    getMessageListSessionKey("session-a"),
    getMessageListSessionKey("session-b"),
  );
  assert.equal(getMessageListSessionKey(null), "__new_session__");
});

test("uses a much tighter bottom threshold on desktop than on mobile", () => {
  assert.equal(getAtBottomThresholdPx(false), 4);
  assert.equal(getAtBottomThresholdPx(true), 120);
  assert.equal(getAutoScrollResumeThresholdPx(false, 16), 48);
  assert.equal(getAutoScrollResumeThresholdPx(true, 96), 120);
  assert.equal(getAwayFromBottomThresholdPx(false, 16), 16);
  assert.equal(getAwayFromBottomThresholdPx(true, 96), 96);
});

test("keeps the mobile footer spacer compact so history loads can settle near the latest message", () => {
  assert.equal(
    getMessageListFooterSpacerClass(true),
    "h-[calc(1.5rem+env(safe-area-inset-bottom))]",
  );
  assert.equal(getMessageListFooterSpacerClass(false), "h-8");
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

  assert.equal(called, true);
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

  assert.equal(scroller.scrollTop, scroller.scrollHeight);
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

  assert.deepEqual(footerArgs, {
    behavior: "auto",
    block: "end",
  });
  assert.equal(scroller.scrollTop, scroller.scrollHeight);
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

  assert.ok(scrollToIndexCalls > 0);
  assert.equal(footerCalls, 0);
  assert.equal(scroller.scrollTop, scroller.scrollHeight);
});

test("treats a top jump right after bottom-locking as recoverable", () => {
  assert.equal(
    shouldIgnoreUnexpectedTopJumpDuringBottomLock({
      scrollTop: 0,
      clientHeight: 600,
      scrollHeight: 2400,
      autoScrollActive: false,
      recentlyBottomLocked: true,
      userScrolledUp: false,
      manualDetachActive: false,
    }),
    true,
  );
});

test("does not recover a top jump after the user intentionally detached", () => {
  assert.equal(
    shouldIgnoreUnexpectedTopJumpDuringBottomLock({
      scrollTop: 0,
      clientHeight: 600,
      scrollHeight: 2400,
      autoScrollActive: false,
      recentlyBottomLocked: true,
      userScrolledUp: true,
      manualDetachActive: false,
    }),
    false,
  );
});

test("clears the unexpected top jump recovery window on user intent", () => {
  assert.equal(
    getUnexpectedTopJumpRecoveryUntilAfterUserIntent({
      recoverUntil: 2000,
      now: 1000,
    }),
    0,
  );

  assert.equal(
    getUnexpectedTopJumpRecoveryUntilAfterUserIntent({
      recoverUntil: 1000,
      now: 2000,
    }),
    1000,
  );
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

  assert.deepEqual(scrollToIndexArgs, {
    index: "LAST",
    align: "end",
    behavior: "auto",
  });
  assert.equal(scroller.scrollTop, 0);
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

  assert.ok(virtuosoScrolls > 0);
  assert.equal(footerScrolls, 0);
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

  assert.ok(autoScrollCalls > 0);
  assert.equal(scrollToCalls, 0);
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

  assert.notEqual(completionReason, "settled");
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
  assert.equal(completionReason, null);

  await new Promise((resolve) => setTimeout(resolve, 100));
  assert.equal(completionReason, "settled");
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

  assert.equal(completionReason, "max-attempts");
  assert.equal(scrollCalls, 3);
});

test("keeps bottom locked when observed layout changes", async () => {
  let observedTarget: unknown = null;
  let resizeCallback: () => void = () => {
    assert.fail("resize observer was not registered");
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
  assert.equal(observedTarget, scroller);

  scroller.scrollHeight = 700;
  resizeCallback();

  assert.equal(scroller.scrollTop, 600);

  stop();
  assert.equal(disconnected, true);
});

test("keeps the resize observer alive past the normal time budget while a streaming lock is active", async () => {
  let resizeCallback: () => void = () => {
    assert.fail("resize observer was not registered");
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
  assert.equal(completionReason, null);
  assert.equal(disconnected, false);

  scroller.scrollHeight = 700;
  resizeCallback();
  assert.equal(scroller.scrollTop, 600);

  keepStreamingLock = false;

  await new Promise((resolve) => setTimeout(resolve, 40));
  assert.equal(completionReason, "settled");
  assert.equal(disconnected, true);
});

test("extends the settle window when observed layout changes keep arriving during history finalize", async () => {
  let resizeCallback: () => void = () => {
    assert.fail("resize observer was not registered");
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
  assert.equal(completionReason, null);

  await new Promise((resolve) => setTimeout(resolve, 40));
  assert.equal(completionReason, "settled");
  assert.equal(scroller.scrollTop, 800);
});

test("keeps history bottom lock alive for late layout shifts after the first settle", async () => {
  let resizeCallback: () => void = () => {
    assert.fail("resize observer was not registered");
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
  assert.equal(completionReason, null);

  scroller.scrollHeight = 900;
  resizeCallback();

  assert.equal(scroller.scrollTop, 800);

  await new Promise((resolve) => setTimeout(resolve, 130));
  assert.equal(completionReason, "settled");
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

  assert.equal(initialSettleCalls, 1);
  assert.equal(completeCalls, 0);

  stop();
});

test("does not keep extending post-settle observation on repeated layout changes", async () => {
  let resizeCallback: () => void = () => {
    assert.fail("resize observer was not registered");
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
  assert.equal(completionReason, null);

  for (let i = 0; i < 3; i += 1) {
    scroller.scrollHeight += 100;
    resizeCallback();
    await new Promise((resolve) => setTimeout(resolve, 25));
  }

  assert.equal(completionReason, "settled");

  scroller.scrollTop = 123;
  scroller.scrollHeight += 100;
  resizeCallback();
  assert.equal(scroller.scrollTop, 123);
});

test("keeps default bottom lock alive briefly for post-stream layout shifts", async () => {
  let resizeCallback: () => void = () => {
    assert.fail("resize observer was not registered");
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
  assert.equal(completionReason, null);

  scroller.scrollHeight = 900;
  resizeCallback();

  assert.equal(scroller.scrollTop, 800);
  assert.equal(completionReason, null);
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
  assert.equal(completionReason, null);

  scroller.scrollTop = 0;
  await new Promise((resolve) => setTimeout(resolve, 15));

  assert.equal(scroller.scrollTop, 400);
  assert.equal(completionReason, null);
});

test("does not pull back to bottom after the user leaves bottom during history settle observation", async () => {
  let resizeCallback: () => void = () => {
    assert.fail("resize observer was not registered");
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
  assert.equal(completionReason, null);

  scroller.scrollTop = 360;
  scroller.scrollHeight = 900;
  resizeCallback();

  assert.equal(scroller.scrollTop, 360);
  assert.equal(completionReason, "aborted");
});

test("does not auto-scroll on viewport changes when the list is not scrollable", () => {
  assert.equal(
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
    false,
  );
});

test("auto-scrolls on viewport changes only when a scrollable list is still bottom-anchored", () => {
  assert.equal(
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
    true,
  );

  assert.equal(
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
    false,
  );
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

  assert.equal(hasOutgoingMessage, true);
});

test("does not treat assistant-only streaming updates or bulk history loads as local sends", () => {
  assert.equal(
    hasNewOutgoingMessage(
      [{ id: "1", role: "user" }],
      [
        { id: "1", role: "user" },
        { id: "2", role: "assistant" },
      ],
    ),
    false,
  );

  assert.equal(
    hasNewOutgoingMessage(
      [],
      [
        { id: "1", role: "user" },
        { id: "2", role: "assistant" },
        { id: "3", role: "user" },
      ],
    ),
    false,
  );
});

test("does not auto-scroll while history loading is still in progress", () => {
  assert.equal(
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
    false,
  );
});

test("does not auto-scroll non-assistant bulk history updates just because the list grew", () => {
  assert.equal(
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
    false,
  );
});

test("does not auto-scroll when multiple messages are appended at once", () => {
  assert.equal(
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
    false,
  );
});

test("treats an early upward mobile user scroll during active follow as an immediate detach", () => {
  assert.equal(
    shouldStopAutoScrollOnUserScroll({
      isMobileViewport: true,
      autoScrollActive: true,
      programmaticScroll: false,
      movedUp: true,
      isAwayFromBottom: false,
      deltaScrollPx: 18,
      scrollTop: 260,
    }),
    true,
  );
});

test("treats an early upward mobile user scroll as a detach even in short transcripts", () => {
  assert.equal(
    shouldStopAutoScrollOnUserScroll({
      isMobileViewport: true,
      autoScrollActive: true,
      programmaticScroll: false,
      movedUp: true,
      isAwayFromBottom: false,
      deltaScrollPx: 12,
      scrollTop: 80,
    }),
    true,
  );
});

test("does not stop auto-scroll for programmatic or tiny upward adjustments", () => {
  assert.equal(
    shouldStopAutoScrollOnUserScroll({
      isMobileViewport: true,
      autoScrollActive: true,
      programmaticScroll: true,
      movedUp: true,
      isAwayFromBottom: true,
      deltaScrollPx: 40,
      scrollTop: 260,
    }),
    false,
  );

  assert.equal(
    shouldStopAutoScrollOnUserScroll({
      isMobileViewport: true,
      autoScrollActive: true,
      programmaticScroll: false,
      movedUp: true,
      isAwayFromBottom: false,
      deltaScrollPx: 1,
      scrollTop: 260,
    }),
    false,
  );
});

test("ignores an unexpected top jump while the bottom lock is still active", () => {
  assert.equal(
    shouldIgnoreUnexpectedTopJumpDuringBottomLock({
      scrollTop: 0,
      clientHeight: 100,
      scrollHeight: 500,
      autoScrollActive: true,
      userScrolledUp: false,
      manualDetachActive: false,
    }),
    true,
  );

  assert.equal(
    shouldIgnoreUnexpectedTopJumpDuringBottomLock({
      scrollTop: 0,
      clientHeight: 100,
      scrollHeight: 500,
      autoScrollActive: true,
      userScrolledUp: true,
      manualDetachActive: false,
    }),
    false,
  );
});

test("treats that same early upward scroll as a detach on desktop too", () => {
  assert.equal(
    shouldStopAutoScrollOnUserScroll({
      isMobileViewport: false,
      autoScrollActive: true,
      programmaticScroll: false,
      movedUp: true,
      isAwayFromBottom: false,
      deltaScrollPx: 18,
      scrollTop: 260,
    }),
    true,
  );
});

test("auto-scrolls appended assistant messages only while the view is bottom-anchored", () => {
  const previousMessages = [{ id: "1", role: "user" }];
  const nextMessages = [
    { id: "1", role: "user" },
    { id: "2", role: "assistant" },
  ];

  assert.equal(
    shouldAutoScrollForMessageUpdate({
      previousMessages,
      nextMessages,
      userScrolledUp: false,
      autoScrollActive: false,
      isNearBottom: true,
    }),
    true,
  );

  assert.equal(
    shouldAutoScrollForMessageUpdate({
      previousMessages,
      nextMessages,
      userScrolledUp: true,
      autoScrollActive: false,
      isNearBottom: false,
    }),
    false,
  );
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

  assert.equal(
    shouldAutoScrollForMessageUpdate({
      previousMessages,
      nextMessages,
      userScrolledUp: false,
      autoScrollActive: false,
      isNearBottom: true,
      shouldMaintainStreamLock: false,
    }),
    true,
  );
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

  assert.equal(
    shouldAutoScrollForMessageUpdate({
      previousMessages,
      nextMessages,
      userScrolledUp: false,
      autoScrollActive: false,
      isNearBottom: false,
      shouldMaintainStreamLock: true,
    }),
    true,
  );
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

  assert.equal(
    shouldAutoScrollForMessageUpdate({
      previousMessages,
      nextMessages,
      userScrolledUp: false,
      autoScrollActive: true,
      isNearBottom: false,
      shouldMaintainStreamLock: true,
    }),
    false,
  );
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

  assert.equal(
    shouldAutoScrollForMessageUpdate({
      previousMessages,
      nextMessages,
      userScrolledUp: false,
      autoScrollActive: false,
      isNearBottom: false,
      shouldMaintainStreamLock: true,
      manualDetachActive: true,
    }),
    false,
  );
});

test("does not auto-scroll a newly appended assistant message while detached", () => {
  const previousMessages = [{ id: "1", role: "user" }];
  const nextMessages = [
    { id: "1", role: "user" },
    { id: "2", role: "assistant" },
  ];

  assert.equal(
    shouldAutoScrollForMessageUpdate({
      previousMessages,
      nextMessages,
      userScrolledUp: false,
      autoScrollActive: false,
      isNearBottom: true,
      manualDetachActive: true,
    }),
    false,
  );
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

  assert.equal(
    shouldAutoScrollForMessageUpdate({
      previousMessages,
      nextMessages,
      userScrolledUp: false,
      autoScrollActive: false,
      isNearBottom: false,
      shouldMaintainStreamLock: false,
    }),
    false,
  );
});
