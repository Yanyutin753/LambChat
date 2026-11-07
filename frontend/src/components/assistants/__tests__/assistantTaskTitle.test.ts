import { expect, test } from "vitest";
import { assistantTaskTitle } from "../assistantTaskTitle";

test("uses an explicit task heading while keeping requirements separate", () => {
  expect(
    assistantTaskTitle("【金额汇总】仅在 task-b 内创建文件。\n运行测试。"),
  ).toBe("金额汇总");
});

test("uses the first sentence or line for an ordinary request", () => {
  expect(assistantTaskTitle("Find useful sources. Verify every link.")).toBe(
    "Find useful sources.",
  );
  expect(assistantTaskTitle("Compare tools\nInclude limitations")).toBe(
    "Compare tools",
  );
});

test("keeps short, punctuation-free titles intact", () => {
  expect(assistantTaskTitle("  调研长期助手  ")).toBe("调研长期助手");
});
