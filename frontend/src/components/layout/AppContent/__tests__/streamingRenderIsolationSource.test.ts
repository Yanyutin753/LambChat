import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { expect, test } from "vitest";

const source = readFileSync(
  resolve(import.meta.dirname, "../ChatView.tsx"),
  { encoding: "utf8" },
);

test("message-dependent row callbacks stay stable across streaming ticks", () => {
  // 流式期间 messages 每个 tick 都换引用；行级回调若依赖 messages，
  // virtuosoItemContent 身份随之变化，所有可见消息行每 tick 全量重渲，
  // 长会话下滑动明显掉帧。回调必须经 messagesRef 读取最新消息。
  const retryDeps = source
    .split("const handleRetryCancelledMessage = useCallback")[1]
    ?.split(");")[0];
  expect(retryDeps).toBeTruthy();
  expect(retryDeps).not.toContain("[canSendMessage, messages,");
  expect(retryDeps).toMatch(/messagesRef\.current/);

  const recommendDeps = source
    .split("const handleRecommendQuestionClick = useCallback")[1]
    ?.split(");")[0];
  expect(recommendDeps).toBeTruthy();
  expect(recommendDeps).not.toContain("messages,");
});

test("pending ask-human scan is memoized instead of per-render flatMap", () => {
  // O(全部 parts) 的扫描每 tick 白跑两遍（sendBlocked + JSX）
  expect(source).toMatch(/const hasPendingAskHumanParts = useMemo/);
  expect(source).toMatch(/hasPendingAskHumanParts/);
});

test("composer onSend keeps a stable identity so memo(ChatInput) holds", () => {
  // onSend 是内联箭头函数时每个 tick 换身份，输入框在流式期间反复重渲
  const onSend = source
    .split("const handleStableSend = useCallback")[1]
    ?.split("\n  );")[0];
  expect(onSend).toBeTruthy();
  expect(onSend).toMatch(/onSendMessageRef\.current/);
  expect(source).toMatch(/onSend: handleStableSend/);
});
