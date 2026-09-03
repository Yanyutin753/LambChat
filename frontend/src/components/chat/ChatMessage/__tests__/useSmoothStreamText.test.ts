/** @vitest-environment jsdom */
/**
 * useSmoothStreamText——流式文案平滑展示：片段到达后逐帧流出（打字机效果），
 * 而非整块蹦出；非流式（历史回放/已完成）直接全量。
 */
import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import { useSmoothStreamText } from "../useSmoothStreamText";

let frames: FrameRequestCallback[] = [];

beforeEach(() => {
  frames = [];
  vi.stubGlobal("requestAnimationFrame", (cb: FrameRequestCallback) => {
    frames.push(cb);
    return frames.length;
  });
  vi.stubGlobal("cancelAnimationFrame", (id: number) => {
    void id;
  });
});
afterEach(() => {
  vi.unstubAllGlobals();
});

/** 推进 n 帧：执行已排队的所有 rAF 回调 */
function tick(n = 1) {
  for (let i = 0; i < n; i++) {
    const cbs = frames.splice(0);
    for (const cb of cbs) cb(0);
  }
}

describe("useSmoothStreamText", () => {
  test("非流式（历史回放/已完成）直接全量展示", () => {
    const { result } = renderHook(() =>
      useSmoothStreamText("整段已完成的内容", false),
    );
    expect(result.current).toBe("整段已完成的内容");
  });

  test("流式：片段到达后逐帧流出，最终追平目标", () => {
    const { result, rerender } = renderHook(
      ({ text, streaming }: { text: string; streaming: boolean }) =>
        useSmoothStreamText(text, streaming),
      { initialProps: { text: "", streaming: true } },
    );

    act(() => {
      rerender({ text: "0123456789", streaming: true });
    });
    act(() => {
      tick(1);
    });
    // 首帧只流出一部分——不是整块蹦出
    expect(result.current.length).toBeGreaterThanOrEqual(1);
    expect(result.current.length).toBeLessThan(10);

    act(() => {
      tick(30);
    });
    expect(result.current).toBe("0123456789");
  });

  test("流式结束（isStreaming→false）立即展示全量", () => {
    const { result, rerender } = renderHook(
      ({ text, streaming }: { text: string; streaming: boolean }) =>
        useSmoothStreamText(text, streaming),
      { initialProps: { text: "", streaming: true } },
    );

    act(() => {
      rerender({ text: "未追平就结束了", streaming: true });
    });
    act(() => {
      rerender({ text: "未追平就结束了", streaming: false });
    });
    expect(result.current).toBe("未追平就结束了");
  });

  test("动画进行中新片段到达：从已展示长度继续，不重放", () => {
    const { result, rerender } = renderHook(
      ({ text, streaming }: { text: string; streaming: boolean }) =>
        useSmoothStreamText(text, streaming),
      { initialProps: { text: "", streaming: true } },
    );

    act(() => {
      rerender({ text: "第一段", streaming: true });
    });
    act(() => {
      tick(1);
    });
    const shownAfterFirst = result.current;
    expect(shownAfterFirst.length).toBeGreaterThan(0);
    expect(shownAfterFirst.length).toBeLessThan(3);

    act(() => {
      rerender({ text: "第一段+第二段", streaming: true });
    });
    act(() => {
      tick(30);
    });
    // 前缀保持连续：已流出的部分不变，只是继续向后追
    expect(result.current.startsWith(shownAfterFirst)).toBe(true);
    expect(result.current).toBe("第一段+第二段");
  });

  test("目标变短（内容重置）时立即对齐", () => {
    const { result, rerender } = renderHook(
      ({ text, streaming }: { text: string; streaming: boolean }) =>
        useSmoothStreamText(text, streaming),
      { initialProps: { text: "", streaming: true } },
    );

    act(() => {
      rerender({ text: "旧内容比较长", streaming: true });
    });
    act(() => {
      tick(30); // 旧内容已全量流出
    });
    expect(result.current).toBe("旧内容比较长");

    act(() => {
      rerender({ text: "新", streaming: true });
    });
    expect(result.current).toBe("新"); // 变短立即对齐，不逐帧回退
  });
});
