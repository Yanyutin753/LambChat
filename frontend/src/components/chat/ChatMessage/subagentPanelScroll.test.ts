import assert from "node:assert/strict";
import test from "node:test";
import {
  isNearSubagentPanelBottom,
  shouldAutoScrollSubagentPanel,
} from "./subagentPanelScroll.ts";

test("detects whether the subagent panel is near the bottom", () => {
  assert.equal(
    isNearSubagentPanelBottom({
      scrollTop: 368,
      clientHeight: 100,
      scrollHeight: 500,
    }),
    true,
  );

  assert.equal(
    isNearSubagentPanelBottom({
      scrollTop: 300,
      clientHeight: 100,
      scrollHeight: 500,
    }),
    false,
  );
});

test("keeps subagent panel bottom-locked unless the user scrolled up", () => {
  const scroller = {
    scrollTop: 0,
    clientHeight: 100,
    scrollHeight: 500,
  };

  assert.equal(
    shouldAutoScrollSubagentPanel({
      scroller,
      userScrolledUp: false,
    }),
    true,
  );

  assert.equal(
    shouldAutoScrollSubagentPanel({
      scroller,
      userScrolledUp: true,
    }),
    false,
  );
});

test("does not auto-scroll before the panel scroller mounts", () => {
  assert.equal(
    shouldAutoScrollSubagentPanel({
      scroller: null,
      userScrolledUp: false,
    }),
    false,
  );
});
