import { useEffect, useRef } from "react";

/**
 * 扫描容器内 [data-reveal] 元素并在进入视口时加 .revealed。
 * `redetect`：异步挂载的内容（如接口返回后才渲染的分区）传入状态依赖，
 * 让 observer 在内容变化后重扫——否则晚挂载的元素永远停在隐藏态。
 */
export function useScrollReveal(redetect?: unknown[]) {
  const containerRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const root = containerRef.current;
    if (!root) return;
    const els = root.querySelectorAll("[data-reveal], [data-reveal-scale]");
    if (!els.length) return;
    const obs = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (entry.isIntersecting) {
            entry.target.classList.add("revealed");
            obs.unobserve(entry.target);
          }
        }
      },
      { rootMargin: "0px 0px -30px 0px", threshold: 0.06 },
    );
    els.forEach((el) => obs.observe(el));
    return () => obs.disconnect();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, redetect ?? []);
  return containerRef;
}
