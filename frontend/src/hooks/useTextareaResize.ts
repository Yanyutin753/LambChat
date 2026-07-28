import { useRef, useEffect, useCallback, useState } from "react";
import {
  getTextareaMaxHeightPx,
  measureComposerExpandVisibility,
  resizeTextareaForContent,
} from "../components/chat/chatInputViewport";

function readTextareaMetrics(el: HTMLTextAreaElement): {
  lineHeight: number;
  verticalPadding: number;
} {
  if (typeof window === "undefined") {
    return { lineHeight: 24, verticalPadding: 10 };
  }
  const style = window.getComputedStyle(el);
  const lineHeight = Number.parseFloat(style.lineHeight);
  const paddingTop = Number.parseFloat(style.paddingTop) || 0;
  const paddingBottom = Number.parseFloat(style.paddingBottom) || 0;
  return {
    lineHeight: Number.isFinite(lineHeight) && lineHeight > 0 ? lineHeight : 24,
    verticalPadding: paddingTop + paddingBottom,
  };
}

export function useTextareaResize(
  textareaRef: React.RefObject<HTMLTextAreaElement | null>,
  input: string,
) {
  const resizeRafRef = useRef<number>(0);
  const [showExpandButton, setShowExpandButton] = useState(false);

  const resizeTextareaHeightNow = useCallback(() => {
    const el = textareaRef.current;
    if (!el) return;
    resizeTextareaForContent(
      el,
      getTextareaMaxHeightPx({
        isMobile:
          typeof window !== "undefined" ? window.innerWidth < 640 : false,
        viewportHeight:
          typeof window !== "undefined"
            ? window.visualViewport?.height ?? window.innerHeight
            : null,
      }),
    );

    // Measure full content height with height:auto semantics via scrollHeight.
    const metrics = readTextareaMetrics(el);
    setShowExpandButton(
      measureComposerExpandVisibility(el, {
        lineHeight: metrics.lineHeight,
        verticalPadding: metrics.verticalPadding,
      }),
    );
  }, [textareaRef]);

  const scheduleTextareaResize = useCallback(() => {
    if (typeof window === "undefined") return;
    cancelAnimationFrame(resizeRafRef.current);
    resizeRafRef.current = requestAnimationFrame(resizeTextareaHeightNow);
  }, [resizeTextareaHeightNow]);

  useEffect(() => {
    requestAnimationFrame(resizeTextareaHeightNow);
  }, [input, resizeTextareaHeightNow]);

  useEffect(() => {
    if (typeof window === "undefined") return undefined;

    const updateTextareaSize = () => scheduleTextareaResize();
    updateTextareaSize();
    window.visualViewport?.addEventListener("resize", updateTextareaSize);
    window.addEventListener("resize", updateTextareaSize);
    window.addEventListener("orientationchange", updateTextareaSize);

    return () => {
      window.visualViewport?.removeEventListener("resize", updateTextareaSize);
      window.removeEventListener("resize", updateTextareaSize);
      window.removeEventListener("orientationchange", updateTextareaSize);
    };
  }, [scheduleTextareaResize]);

  useEffect(() => {
    return () => cancelAnimationFrame(resizeRafRef.current);
  }, []);

  return { scheduleTextareaResize, showExpandButton };
}
