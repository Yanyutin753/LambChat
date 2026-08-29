import { expect, test } from "vitest";

import {
  createWheelIntentAccumulator,
  nextWheelIntentState,
} from "../messageScrollUtils";

test("single strong upward wheel detaches immediately", () => {
  const result = nextWheelIntentState(
    createWheelIntentAccumulator(),
    -24,
    1_000,
  );
  expect(result.detach).toBe(true);
});

test("trackpad inertia: sub-threshold upward wheels accumulate to detach", () => {
  let state = createWheelIntentAccumulator();
  // 一串 -4px 的惯性微上滑：单个不到 6px 阈值，但 300ms 内累计 24px 应脱钉
  const deltas = [-4, -4, -4, -4, -4, -4];
  let detached = false;
  deltas.forEach((delta, index) => {
    const result = nextWheelIntentState(state, delta, 1_000 + index * 16);
    state = result.state;
    if (result.detach) detached = true;
  });
  expect(detached).toBe(true);
});

test("sporadic micro-jitters far apart do not accumulate", () => {
  let state = createWheelIntentAccumulator();
  // 相邻事件间隔远超 300ms 窗口：各自清零，不累计成意图
  [0, 2_000, 4_000, 6_000, 7_000, 9_000].forEach((ts, index) => {
    const result = nextWheelIntentState(state, -5, ts);
    state = result.state;
    if (index === 5) expect(result.detach).toBe(false);
  });
});

test("downward wheel resets the accumulator and keeps following", () => {
  const state = nextWheelIntentState(
    createWheelIntentAccumulator(),
    -5,
    1_000,
  ).state;
  const result = nextWheelIntentState(state, 8, 1_050);
  expect(result.detach).toBe(false);
  expect(result.state.upwardPx).toBe(0);

  // 下滑清零后，新的微上滑从零开始累计
  const after = nextWheelIntentState(result.state, -5, 1_100);
  expect(after.detach).toBe(false);
  expect(after.state.upwardPx).toBe(5);
});

test("zero-delta (horizontal) events do not count as upward intent", () => {
  const result = nextWheelIntentState(
    { upwardPx: 20, lastWheelTs: 1_000 },
    0,
    1_016,
  );
  expect(result.detach).toBe(false);
  expect(result.state.upwardPx).toBe(0);
});
