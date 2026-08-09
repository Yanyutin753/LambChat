import {
  useEffect,
  useLayoutEffect,
  useRef,
  useSyncExternalStore,
  type RefObject,
} from "react";

import type { RightPanelPresentation } from "../../hooks/rightPanelLayout";
import {
  getRightPanelSnapshot,
  registerRightPanel,
  subscribeRightPanels,
  unregisterRightPanel,
  updateRightPanel,
  type RightPanelKind,
} from "./rightPanelCoordinator";

export function useRightPanelEntry({
  open,
  onClose,
  kind,
  automatic = false,
}: {
  open: boolean;
  onClose: () => void;
  kind: RightPanelKind;
  automatic?: boolean;
}) {
  const ownerId = useRef(Symbol(`right-panel:${kind}`)).current;
  const openerRef = useRef<HTMLElement | null>(null);
  const closeRef = useRef(onClose);
  const automaticRef = useRef(automatic);
  closeRef.current = onClose;
  automaticRef.current = automatic;

  const snapshot = useSyncExternalStore(
    subscribeRightPanels,
    getRightPanelSnapshot,
    getRightPanelSnapshot,
  );

  useLayoutEffect(() => {
    if (!open) return;

    openerRef.current =
      document.activeElement instanceof HTMLElement
        ? document.activeElement
        : null;
    const accepted = registerRightPanel({
      id: ownerId,
      kind,
      automatic: automaticRef.current,
      close: () => closeRef.current(),
      opener: openerRef.current,
    });
    if (!accepted) return;

    return () => unregisterRightPanel(ownerId);
  }, [open, ownerId, kind]);

  useLayoutEffect(() => {
    if (!open || snapshot.activeId !== ownerId) return;

    updateRightPanel({
      id: ownerId,
      kind,
      automatic,
      close: () => closeRef.current(),
      opener: openerRef.current,
    });
  }, [open, ownerId, kind, automatic, snapshot.activeId]);

  return {
    ownerId,
    active: open && snapshot.activeId === ownerId,
    hasPrevious: open && snapshot.activeId === ownerId && snapshot.depth > 1,
    openerRef,
  };
}

const FOCUSABLE =
  'a[href],button:not([disabled]),input:not([disabled]),select:not([disabled]),textarea:not([disabled]),[tabindex]:not([tabindex="-1"])';

function restoreOpenerFocus(openerRef: RefObject<HTMLElement | null>): void {
  requestAnimationFrame(() => {
    if (openerRef.current?.isConnected) {
      openerRef.current.focus({ preventScroll: true });
    }
  });
}

export function useRightPanelFocus({
  open,
  active,
  automatic,
  presentation,
  panelRef,
  openerRef,
}: {
  open: boolean;
  active: boolean;
  automatic: boolean;
  presentation: RightPanelPresentation;
  panelRef: RefObject<HTMLElement | null>;
  openerRef: RefObject<HTMLElement | null>;
}): void {
  const wasActive = useRef(false);
  const wasOpen = useRef(false);

  useEffect(() => {
    if (active && !wasActive.current && !automatic) {
      queueMicrotask(() => {
        const panel = panelRef.current;
        const first = panel?.querySelector<HTMLElement>(FOCUSABLE);
        (first ?? panel)?.focus({ preventScroll: true });
      });
    }

    if (!open && wasOpen.current) {
      restoreOpenerFocus(openerRef);
    }

    wasActive.current = active;
    wasOpen.current = open;
  }, [active, automatic, open, openerRef, panelRef]);

  useEffect(
    () => () => {
      if (!wasActive.current) return;
      restoreOpenerFocus(openerRef);
    },
    [openerRef],
  );

  useEffect(() => {
    if (!active || presentation === "docked") return;

    const root = document.getElementById("root");
    const previousInert = root?.inert ?? false;
    if (root) root.inert = true;

    const trapTab = (event: KeyboardEvent) => {
      if (event.key !== "Tab") return;

      const focusable = [
        ...(panelRef.current?.querySelectorAll<HTMLElement>(FOCUSABLE) ?? []),
      ].filter((element) => !element.hidden && element.tabIndex >= 0);
      if (focusable.length === 0) return;

      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };

    document.addEventListener("keydown", trapTab);
    return () => {
      document.removeEventListener("keydown", trapTab);
      if (root) root.inert = previousInert;
    };
  }, [active, presentation, panelRef]);
}
