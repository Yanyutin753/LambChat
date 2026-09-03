import { useEffect, useRef, useState } from "react";

/**
 * 流式文案平滑展示：片段（chunk）到达后逐帧流出，呈现打字机效果而非整块
 * 蹦出。每帧流出量随积压量按比例增长（backlog/divisor，下限 2 字），任何
 * 大小的片段都约 12 帧（~200ms）追平——平滑但不拖尾。
 *
 * 非流式（历史回放/已完成）直接全量展示，不做动画。
 */
const BACKLOG_DIVISOR = 12;
const MIN_CHARS_PER_FRAME = 2;

export function useSmoothStreamText(target: string, isStreaming: boolean) {
  const [shown, setShown] = useState(() => (isStreaming ? "" : target));
  const shownRef = useRef(shown);

  useEffect(() => {
    if (!isStreaming || target.length < shownRef.current.length) {
      // 非流式 / 内容重置：立即对齐
      shownRef.current = target;
      setShown(target);
      return;
    }
    if (target.length === shownRef.current.length) return;

    let raf = 0;
    const step = () => {
      const backlog = target.length - shownRef.current.length;
      if (backlog <= 0) return;
      const advance = Math.max(
        MIN_CHARS_PER_FRAME,
        Math.ceil(backlog / BACKLOG_DIVISOR),
      );
      shownRef.current = target.slice(0, shownRef.current.length + advance);
      setShown(shownRef.current);
      if (shownRef.current.length < target.length) {
        raf = requestAnimationFrame(step);
      }
    };
    raf = requestAnimationFrame(step);
    return () => cancelAnimationFrame(raf);
  }, [target, isStreaming]);

  return isStreaming ? shown : target;
}
