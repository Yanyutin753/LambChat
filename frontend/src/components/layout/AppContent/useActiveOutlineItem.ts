import { useEffect, useState, useRef, useCallback } from "react";
import type { MessageOutlineItem } from "./messageOutline";

export function useActiveOutlineItem(
  outlineItems: MessageOutlineItem[],
  scrollerRef: React.RefObject<HTMLDivElement | null>,
): string | null {
  const [activeId, setActiveId] = useState<string | null>(null);
  const observerRef = useRef<IntersectionObserver | null>(null);

  const buildRootMargin = useCallback(() => {
    const scroller = scrollerRef.current;
    if (!scroller) return "0px";
    const height = scroller.clientHeight;
    const top = Math.floor(height * 0.2);
    const bottom = Math.floor(height * 0.6);
    return `-${top}px 0px -${bottom}px 0px`;
  }, [scrollerRef]);

  useEffect(() => {
    observerRef.current?.disconnect();
    observerRef.current = null;

    const scroller = scrollerRef.current;
    if (outlineItems.length === 0 || !scroller) {
      setActiveId(null);
      return;
    }

    const anchorIds = new Set(outlineItems.map((item) => item.anchorId));
    const visibleAnchors = new Map<string, number>();

    const updateActive = () => {
      if (visibleAnchors.size === 0) {
        setActiveId(null);
        return;
      }
      let bestId: string | null = null;
      let bestTop = -Infinity;
      for (const [id, top] of visibleAnchors) {
        if (top > bestTop) {
          bestTop = top;
          bestId = id;
        }
      }
      setActiveId(bestId);
    };

    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          const id = entry.target.getAttribute("data-outline-id");
          if (!id || !anchorIds.has(id)) continue;

          if (entry.isIntersecting) {
            const rect = entry.boundingClientRect;
            visibleAnchors.set(id, rect.top);
          } else {
            visibleAnchors.delete(id);
          }
        }
        updateActive();
      },
      {
        root: scroller,
        rootMargin: buildRootMargin(),
        threshold: [0, 0.25, 0.5, 1],
      },
    );

    observerRef.current = observer;

    for (const item of outlineItems) {
      const el = document.getElementById(item.anchorId);
      if (el) {
        observer.observe(el);
      }
    }

    return () => {
      observer.disconnect();
    };
  }, [outlineItems, scrollerRef, buildRootMargin]);

  return activeId;
}
