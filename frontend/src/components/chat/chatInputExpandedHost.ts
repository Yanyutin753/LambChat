import { useLayoutEffect, useRef, useState } from "react";

/**
 * Renders the expanded composer at body level without remounting it.
 *
 * The expanded composer is `position: fixed; z-index: 280`, a slot between
 * the body-level tool console (z-200/201) and the dialog band (z-299+).
 * Inside the app shell those z-indexes are trapped by ancestor stacking
 * contexts (AppShell `transform` + `relative z-0`), so body-level overlays
 * paint above the composer no matter how high its z-index is.
 *
 * The ChatInput container renders into a stable host through a portal. While
 * expanded, the host is reparented into `document.body`, restoring the
 * intended stacking order. Reparenting the host — instead of re-portal-ing
 * the subtree — keeps the rich composer mounted, preserving the draft (text,
 * file references, undo history) across expand/collapse.
 */
export function useExpandedComposerHost(expanded: boolean) {
  const [host] = useState<HTMLDivElement | null>(() =>
    typeof document === "undefined" ? null : document.createElement("div"),
  );
  const slotRef = useRef<HTMLDivElement>(null);
  useLayoutEffect(() => {
    if (!host) return;
    const slot = slotRef.current;
    if (!host.parentNode && slot) {
      slot.appendChild(host);
    }
    if (!expanded) return;
    document.body.appendChild(host);
    return () => {
      if (slot && slot.isConnected) slot.appendChild(host);
      else host.remove();
    };
  }, [expanded, host]);
  return { host, slotRef };
}
