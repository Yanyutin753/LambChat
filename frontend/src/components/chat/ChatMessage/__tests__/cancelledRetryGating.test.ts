import { readFileSync } from "node:fs";

const source = readFileSync(new URL("../index.tsx", import.meta.url), "utf-8");

test("插话封存的已停止轮次不提供重试：取消块的重试仅限会话末尾消息", () => {
  // steer 打断的封存轮次不是会话最后一条（后面还有插话与新回答），
  // findCancelledRetryTarget 会错误地取到插话消息重发，必须被 isLastMessage 挡住
  expect(source).toMatch(
    /isLastMessage\s*&&\s*group\.part\.type === "cancelled"\s*&&\s*onRetryCancelledMessage/,
  );
});
