import { readFileSync } from "node:fs";
import { resolve } from "node:path";

const baseCss = readFileSync(resolve(import.meta.dirname, "../base.css"), {
  encoding: "utf8",
});

function readGlobalShellRule(css: string): string {
  return css.match(/html,\s*body,\s*#root\s*\{([^}]*)\}/)?.[1] ?? "";
}

const shellRule = readGlobalShellRule(baseCss);

test("global shell rule does not forbid horizontal touch panning", () => {
  // touch-action 在祖先链上取交集：html/body/#root 上的 pan-y 会禁掉
  // 应用内所有横向滚动容器（markdown 表格、代码块等）的手机端触摸滑动。
  expect(shellRule).not.toMatch(/touch-action:\s*none/);
  expect(shellRule).not.toMatch(/touch-action:\s*pan-y\b/);
  expect(shellRule).not.toMatch(/touch-action:\s*pan-x\b/);
});

test("global shell rule keeps app-like tap behavior via touch-action manipulation", () => {
  // manipulation = pan-x + pan-y + pinch-zoom，仅禁双击缩放，
  // 保留原始提交消除双击缩放延迟的意图。
  expect(shellRule).toMatch(/touch-action:\s*manipulation/);
});
