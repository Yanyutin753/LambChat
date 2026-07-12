import { useRef, useState, useCallback, useEffect } from "react";

/**
 * Tracks the position of a button ref so a dropdown can be anchored below it.
 * Call `update()` to start tracking; position dynamically follows on resize/scroll.
 * Call `update` again with a null ref or close the dropdown to stop tracking.
 */
export function useDropdownPos() {
  const ref = useRef<HTMLButtonElement>(null);
  const [pos, setPos] = useState<{
    top: number;
    left: number;
    right: number;
  } | null>(null);

  const update = useCallback(() => {
    if (!ref.current) return;
    const r = ref.current.getBoundingClientRect();
    setPos({
      top: r.bottom + 6,
      left: r.left,
      right: window.innerWidth - r.right,
    });
  }, []);
  const isTrackingDropdown = pos !== null;

  // Once we have a position, dynamically track on resize/scroll
  useEffect(() => {
    if (!isTrackingDropdown) return;
    let raf = 0;
    const sync = () => {
      cancelAnimationFrame(raf);
      raf = requestAnimationFrame(() => {
        if (!ref.current) return;
        const r = ref.current.getBoundingClientRect();
        setPos({
          top: r.bottom + 6,
          left: r.left,
          right: window.innerWidth - r.right,
        });
      });
    };
    window.addEventListener("resize", sync);
    window.addEventListener("scroll", sync, true);
    return () => {
      cancelAnimationFrame(raf);
      window.removeEventListener("resize", sync);
      window.removeEventListener("scroll", sync, true);
    };
  }, [isTrackingDropdown]);

  return { ref, pos, update };
}
