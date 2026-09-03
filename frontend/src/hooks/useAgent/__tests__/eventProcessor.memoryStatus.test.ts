/**
 * status{stage:memory|memory_done}——首轮记忆装配进度进消息流，
 * 渲染为与沙箱初始化完全同款的状态 item（loading pill → success pill）。
 */
import { processMessageEvent } from "../eventProcessor.ts";

const ARGS = ["", [], 0, [], true, "message-1"] as const;

test("status memory 创建 starting 记忆状态 part", () => {
  const result = processMessageEvent(
    "status",
    { stage: "memory", timestamp: "2026-09-03T12:00:00+00:00" },
    [],
    ...ARGS,
  );

  expect(result.parts).toHaveLength(1);
  expect(result.parts[0]).toMatchObject({
    type: "memoryStatus",
    status: "starting",
    startedAt: "2026-09-03T12:00:00+00:00",
  });
});

test("memory_done 把同一 part 翻成 ready（记录 completedAt，不新增）", () => {
  const started = processMessageEvent(
    "status",
    { stage: "memory", timestamp: "2026-09-03T12:00:00+00:00" },
    [],
    ...ARGS,
  );

  const done = processMessageEvent(
    "status",
    { stage: "memory_done", timestamp: "2026-09-03T12:00:02+00:00" },
    started.parts,
    ...ARGS,
  );

  expect(done.parts).toHaveLength(1);
  expect(done.parts[0]).toMatchObject({
    type: "memoryStatus",
    status: "ready",
    startedAt: "2026-09-03T12:00:00+00:00",
    completedAt: "2026-09-03T12:00:02+00:00",
  });
});

test("memory_done 先到（SSE 重放同批/丢失 start）也能落成 ready part", () => {
  const done = processMessageEvent(
    "status",
    { stage: "memory_done", timestamp: "2026-09-03T12:00:02+00:00" },
    [],
    ...ARGS,
  );

  expect(done.parts).toHaveLength(1);
  expect(done.parts[0]).toMatchObject({ type: "memoryStatus", status: "ready" });
});

test("其他 status stage 不产生 part", () => {
  const result = processMessageEvent("status", { stage: "other" }, [], ...ARGS);
  expect(result.parts).toHaveLength(0);
});
