/** AgentOptionButton 弹层滚动契约：三个变体（居中/移动 sheet/桌面下拉）都必须
 * 有 maxHeight + overflowY——沙箱面板内容超高（执行设备 + 执行策略两段）时，
 * 没有滚动会把底部条目裁成不可点（手机网页端「无需确认」不可达的根因）。 */

import { readFileSync } from "node:fs";
import { resolve } from "node:path";

test("all dropdown variants scroll when content exceeds maxHeight", () => {
  const source = readFileSync(
    resolve(import.meta.dirname, "../AgentOptionButton.tsx"),
    "utf8",
  );
  const sheetStyles = source.match(/maxHeight: "60dvh",/g) ?? [];
  expect(sheetStyles.length).toBe(2); // 居中变体 + 移动 sheet 变体
  const scrollables = source.match(/overflowY: "auto",/g) ?? [];
  expect(scrollables.length).toBe(3); // 上述两个 + 桌面下拉
  expect(source).toMatch(/overscrollBehavior: "contain",/);
  // 桌面下拉必须有自身高度上限（原本完全没有）
  expect(source).toMatch(/maxHeight: "calc\(100dvh - 8rem\)"/);
});
