import {
  isNearSubagentPanelBottom,
  startSubagentPanelScrollToBottom,
  shouldAutoScrollSubagentPanel,
} from "../subagentPanelScroll.ts";

test("detects whether the subagent panel is near the bottom", () => {
  expect(
    isNearSubagentPanelBottom({
      scrollTop: 368,
      clientHeight: 100,
      scrollHeight: 500,
    }),
  ).toBe(true);

  expect(
    isNearSubagentPanelBottom({
      scrollTop: 300,
      clientHeight: 100,
      scrollHeight: 500,
    }),
  ).toBe(false);
});

test("keeps subagent panel bottom-locked unless the user scrolled up", () => {
  const scroller = {
    scrollTop: 0,
    clientHeight: 100,
    scrollHeight: 500,
  };

  expect(
    shouldAutoScrollSubagentPanel({
      scroller,
      userScrolledUp: false,
    }),
  ).toBe(true);

  expect(
    shouldAutoScrollSubagentPanel({
      scroller,
      userScrolledUp: true,
    }),
  ).toBe(false);
});

test("does not auto-scroll before the panel scroller mounts", () => {
  expect(
    shouldAutoScrollSubagentPanel({
      scroller: null,
      userScrolledUp: false,
    }),
  ).toBe(false);
});

test("keeps scrolling to the subagent panel bottom while content height is settling", async () => {
  const scroller = {
    scrollTop: 0,
    clientHeight: 100,
    scrollHeight: 500,
  };

  const stop = startSubagentPanelScrollToBottom({
    scroller,
    intervalMs: 5,
    maxAttempts: 6,
  });

  expect(scroller.scrollTop).toBe(500);

  scroller.scrollHeight = 900;

  await new Promise((resolve) => setTimeout(resolve, 15));
  stop();

  expect(scroller.scrollTop).toBe(900);
});
