import { readFileSync } from "node:fs";
import { resolve } from "node:path";

const css = readFileSync(
  resolve(__dirname, "../../../styles/chat.css"),
  "utf8",
);

const usageChipSource = readFileSync(
  resolve(__dirname, "../ComposerUsageChip.tsx"),
  "utf8",
);

/** 提取 chat.css 中指定选择器的规则块（不含嵌套媒体查询内的覆盖） */
function ruleBlock(selector: string): string {
  const match = css.match(new RegExp(`${selector}\\s*\\{([^}]*)\\}`));
  expect(match).not.toBeNull();
  return match![1];
}

test("chat-tool-btn 固定 2.25rem 高：工具栏各按钮 hover 背景同高", () => {
  const block = ruleBlock("\\.chat-tool-btn");
  // 右簇（沙箱 chip / 用量 chip / 运行模式）与发送键 h-9 全部统一 36px，
  // hover 圆角背景高度一致，不被内容行高撑开
  expect(block).toMatch(/height:\s*2\.25rem/);
  expect(block).not.toMatch(/min-height/);
});

test("chat-tool-btn 仅保留水平 padding，垂直居中交给固定高度", () => {
  const block = ruleBlock("\\.chat-tool-btn");
  // text-base 金额（行高 24px）+ 上下 padding 会把按钮撑到 40px；
  // 垂直间距改由 height + flex 居中承担，padding 只留水平方向
  expect(block).toMatch(/padding:\s*0 0\.5rem/);
});

test("用量 chip 字号保持 text-base 不缩水（高度修复在 CSS 层而非砍字号）", () => {
  expect(usageChipSource).toMatch(/text-base font-semibold/);
});
