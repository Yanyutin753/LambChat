import { readFileSync } from "node:fs";

const source = readFileSync(
  new URL("../UserMessageBubble.tsx", import.meta.url),
  "utf8",
);

// 操作行是 justify-end 的 flex 行，DOM 顺序即视觉从左到右顺序；
// 让复制按钮（含 extraActions 注入的书签等）中位于最右侧，即渲染在最后。
test("copy is the rightmost action in the user message action row", () => {
  const rowStart = source.indexOf('className="flex justify-end mt-2 gap-1"');
  expect(rowStart).toBeGreaterThan(-1);

  const actionRow = source.slice(rowStart);
  const extraActionsIndex = actionRow.indexOf("{extraActions}");
  const copyIndex = actionRow.indexOf("onClick={handleCopy}");

  expect(extraActionsIndex).toBeGreaterThan(-1);
  expect(copyIndex).toBeGreaterThan(extraActionsIndex);
});
