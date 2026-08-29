import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, test } from "vitest";

/** 锁定消息列表滚动抖动容差：轻微波动不得脱离流式跟随。
 *  上方内容回流（过程折叠区展开/收起、代码块渲染）会把视口顶起几像素，
 *  这些波动既不算「上滚」（movedUp 需超过 8px），也不算「上滚意图」
 *  （wheel deltaY 需小于 -6），跟随底部锁定因此不会被误打断。 */
describe("message list scroll jitter tolerance (source)", () => {
  const hookSource = readFileSync(
    resolve(
      process.cwd(),
      "src/components/layout/AppContent/useMessageScroll.hook.ts",
    ),
    "utf8",
  );

  test("ignores upward viewport drift of up to 8px as reflow jitter", () => {
    expect(hookSource).toMatch(
      /const movedUp = scrollTop < lastScrollTop\.value - 8;/,
    );
  });

  test("requires a deliberate upward wheel intent to detach follow", () => {
    // 单次 -6px 以内的微滑不算意图；触控板惯性按 300ms 时间窗累计 24px 判定
    // （nextWheelIntentState），累计前的微滑由底部锁定保持跟随
    expect(hookSource).toMatch(/nextWheelIntentState\(/);
    const utilsSource = readFileSync(
      resolve(
        process.cwd(),
        "src/components/layout/AppContent/messageScrollUtils.ts",
      ),
      "utf8",
    );
    expect(utilsSource).toMatch(/WHEEL_DETACH_SINGLE_PX = 6/);
    expect(utilsSource).toMatch(/WHEEL_DETACH_CUMULATIVE_PX = 24/);
  });

  test("rebinding scroll listeners keeps the real scrollTop baseline", () => {
    // 监听随 messages.length 重绑（流式每追加一条都重绑一次）；基线若归零，
    // 重绑后的第一次真实上滚会因 movedUp 误判为 false 而拉回底部
    expect(hookSource).toMatch(
      /const lastScrollTop = \{ value: scroller\.scrollTop \};/,
    );
  });
});
