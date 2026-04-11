import test from "node:test";
import assert from "node:assert/strict";
import {
  hasNewOutgoingMessage,
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

  await new Promise((resolve) => setTimeout(resolve, 3));
  scroller.scrollTop = 400;
  await new Promise((resolve) => setTimeout(resolve, 3));
  stop();

  assert.ok(scrollCalls.length >= 2);
  assert.deepEqual(scrollCalls[0], {
    top: Number.MAX_SAFE_INTEGER,
    behavior: "auto",
  });
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
