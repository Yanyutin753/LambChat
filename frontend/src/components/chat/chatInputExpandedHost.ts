import { useEffect, useLayoutEffect, useRef, useState } from "react";

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
export function useExpandedComposerHost(
  expanded: boolean,
  setExpanded: (expanded: boolean) => void,
) {
  const [host] = useState<HTMLDivElement | null>(() => {
    if (typeof document === "undefined") return null;
    const element = document.createElement("div");
    element.dataset.chatComposerHost = "";
    return element;
  });
  const slotRef = useRef<HTMLDivElement>(null);
  useLayoutEffect(() => {
    if (!host) return;
    const target = expanded ? document.body : slotRef.current;
    // React can replace the slot during a layout change or hot update.
    // Reattach the existing editor, preserving its draft and undo history.
    if (target && host.parentNode !== target) {
      const active = document.activeElement;
      const focused = active instanceof HTMLElement && host.contains(active);
      const selection = focused ? window.getSelection() : null;
      const anchor = selection?.anchorNode;
      const focus = selection?.focusNode;
      const anchorOffset = selection?.anchorOffset ?? 0;
      const focusOffset = selection?.focusOffset ?? 0;
      target.appendChild(host);
      // Reparenting blurs the editor and clears the browser selection.
      if (focused) {
        active.focus({ preventScroll: true });
        if (anchor && focus && host.contains(anchor) && host.contains(focus)) {
          selection?.setBaseAndExtent(anchor, anchorOffset, focus, focusOffset);
        }
      }
    }
  });
  useLayoutEffect(() => () => host?.remove(), [host]);
  useEffect(() => {
    if (!expanded) return;
    const collapseOnEscape = (event: KeyboardEvent) => {
      if (
        event.key !== "Escape" ||
        event.defaultPrevented ||
        event.isComposing ||
        event.keyCode === 229 ||
        host?.inert
      )
        return;
      event.preventDefault();
      setExpanded(false);
    };
    document.addEventListener("keydown", collapseOnEscape);
    return () => document.removeEventListener("keydown", collapseOnEscape);
  }, [expanded, host, setExpanded]);
  return { host, slotRef };
}
