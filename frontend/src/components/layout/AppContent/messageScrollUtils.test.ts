import test from "node:test";
import assert from "node:assert/strict";
import {
  forceScrollerToPhysicalBottom,
  forceVirtuosoToBottom,
  getAutoScrollResumeThresholdPx,
  getAtBottomThresholdPx,
  getAwayFromBottomThresholdPx,
  getInitialBottomItemLocation,
  hasNewOutgoingMessage,
  shouldAutoScrollForMessageUpdate,
  shouldAutoScrollAfterViewportChange,
  startVirtuosoScrollToBottom,
} from "./messageScrollUtils.ts";

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

test("initializes history at the bottom edge of the latest message", () => {
  assert.deepEqual(getInitialBottomItemLocation(3), {
    index: 2,
    align: "end",
  });

  assert.equal(getInitialBottomItemLocation(0), undefined);
});

test("uses a much tighter bottom threshold on desktop than on mobile", () => {
  assert.equal(getAtBottomThresholdPx(false), 4);
  assert.equal(getAtBottomThresholdPx(true), 120);
  assert.equal(getAutoScrollResumeThresholdPx(false, 16), 48);
  assert.equal(getAutoScrollResumeThresholdPx(true, 96), 120);
  assert.equal(getAwayFromBottomThresholdPx(false, 16), 16);
  assert.equal(getAwayFromBottomThresholdPx(true, 96), 96);
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

test("keeps bottom-lock pinned to the physical scroller bottom when footer is available", async () => {
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
      scroller.scrollTop = scroller.scrollHeight - scroller.clientHeight;
    },
  };

  startVirtuosoScrollToBottom({
    virtuoso,
    scroller,
    footer,
    preferPhysicalBottom: true,
    intervalMs: 1,
    maxAttempts: 5,
  });

  await new Promise((resolve) => setTimeout(resolve, 20));

  assert.ok(footerCalls > 0);
  assert.equal(scrollToIndexCalls, 0);
  assert.equal(scroller.scrollTop, scroller.scrollHeight);
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
  assert.equal(scroller.scrollTop, scroller.scrollHeight);
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

test("allows bulk history loads to bottom-lock when the latest message is assistant", () => {
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
    }),
    true,
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
