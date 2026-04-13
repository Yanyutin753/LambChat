import { useState, useEffect, type ReactNode } from "react";

/**
 * Keeps children mounted for `delay` ms after `show` becomes false.
 * Prevents visual flash when swapping between two full-screen portals/panels.
 */
export function DelayedUnmount({
  show,
  delay = 80,
  children,
}: {
  show: boolean;
  delay?: number;
  children: ReactNode;
}) {
  const [mounted, setMounted] = useState(show);

  useEffect(() => {
    if (show) {
      setMounted(true);
    } else {
      const t = setTimeout(() => setMounted(false), delay);
      return () => clearTimeout(t);
    }
  }, [show, delay]);

  return mounted ? <>{children}</> : null;
}
