import test from "node:test";
import assert from "node:assert/strict";
import {
  getInitialBottomItemLocation,
  hasNewOutgoingMessage,
  shouldAutoScrollForMessageUpdate,
  shouldAutoScrollAfterViewportChange,
  startVirtuosoScrollToBottom,
} from "./messageScrollUtils.ts";

test("keeps asking Virtuoso to scroll until the scroller reaches the bottom", async () => {
  const scrollCalls: Array<{ top: number; behavior: string }> = [];
  const virtuoso = {
    scrollTo: (args: { top: number; behavior: string }) => {
      scrollCalls.push(args);
    },
  };
  const scroller = {
    scrollTop: 0,
    clientHeight: 100,
    scrollHeight: 500,
  };

  const stop = startVirtuosoScrollToBottom({
    virtuoso,
    scroller,
    intervalMs: 1,
    maxAttempts: 5,
  });

  await new Promise((resolve) => setTimeout(resolve, 20));
  scroller.scrollTop = 400;
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

test("uses the footer sentinel even when Virtuoso is available", async () => {
  let footerScrolls = 0;
  const virtuoso = {
    scrollTo: () => undefined,
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

  assert.ok(footerScrolls > 0);
  assert.equal(scroller.scrollTop, 400);
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

test("keeps streaming message updates bottom-locked without stealing history scrollback", () => {
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
    }),
    true,
  );

  assert.equal(
    shouldAutoScrollForMessageUpdate({
      previousMessages,
      nextMessages,
      userScrolledUp: true,
      autoScrollActive: true,
      isNearBottom: false,
    }),
    false,
  );
});
