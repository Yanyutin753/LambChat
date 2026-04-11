import { useState, useCallback, useRef } from "react";

/**
 * Tracks the position of a button ref so a dropdown can be anchored below it.
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

  return { ref, pos, update };
}
