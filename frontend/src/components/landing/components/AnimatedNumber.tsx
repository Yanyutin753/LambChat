import { useEffect, useRef, useState } from "react";

export function AnimatedNumber({ value }: { value: string }) {
  const [display, setDisplay] = useState(value);
  const ref = useRef<HTMLSpanElement>(null);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const m = value.match(/^(\d+)/);
    if (!m) return;
    const num = parseInt(m[1]);
    const suf = value.slice(m[1].length);
    let start = 0;
    const obs = new IntersectionObserver(
      ([e]) => {
        if (e.isIntersecting) {
          const step = (ts: number) => {
            if (!start) start = ts;
            const p = Math.min((ts - start) / 1400, 1);
            setDisplay(
              Math.round((1 - Math.pow(1 - p, 4)) * num).toString() + suf,
            );
            if (p < 1) requestAnimationFrame(step);
          };
          requestAnimationFrame(step);
          obs.unobserve(el);
        }
      },
      { threshold: 0.5 },
    );
    obs.observe(el);
    return () => obs.disconnect();
  }, [value]);
  return <span ref={ref}>{display}</span>;
}
