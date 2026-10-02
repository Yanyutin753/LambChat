import {
  topmostVisibleDialog,
  topmostVisibleModalDialog,
} from "../../utils/modalDialog";
import {
  createContext,
  useContext,
  useEffect,
  useLayoutEffect,
  useRef,
  useId,
  useSyncExternalStore,
  type RefObject,
  type ReactNode,
} from "react";

import { useBodyScrollLock } from "../../hooks/useBodyScrollLock";
import type { RightPanelPresentation } from "../../hooks/rightPanelLayout";
import {
  getRightPanelSnapshot,
  registerRightPanel,
  subscribeRightPanels,
  unregisterRightPanel,
  updateRightPanel,
  type RightPanelKind,
} from "./rightPanelCoordinator";

// Keep imperative viewers mounted; only live subscriptions opt into visibility.
export const RightPanelActiveContext = createContext(true);

export const RightPanelOwnerContext = createContext<symbol | null>(null);

export function useRightPanelEntry({
  open,
  onClose,
  kind,
  automatic = false,
  title,
  icon,
  registryKey,
}: {
  open: boolean;
  onClose: () => void;
  kind: RightPanelKind;
  automatic?: boolean;
  title?: string;
  icon?: ReactNode;
  registryKey?: string;
}) {
  const ownerId = useRef(Symbol(`right-panel:${kind}`)).current;
  const panelId = useId();
  const parentId = useContext(RightPanelOwnerContext);
  const openerRef = useRef<HTMLElement | null>(null);
  const closeRef = useRef(onClose);
  const automaticRef = useRef(automatic);
  closeRef.current = onClose;
  automaticRef.current = automatic;

  // Subscribe to flags, so unrelated tab metadata cannot rerender hidden shells.
  const getFlags = () => {
    const current = getRightPanelSnapshot();
    return (current.activeId === ownerId ? 1 : 0) | (current.depth > 1 ? 2 : 0);
  };
  const flags = useSyncExternalStore(subscribeRightPanels, getFlags, getFlags);

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
      title,
      icon,
      panelId,
      registryKey,
      parentId,
    });
    if (!accepted) return;

    return () => unregisterRightPanel(ownerId);
    // Metadata is updated separately without reordering or activating this tab.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, ownerId, kind]);

  useLayoutEffect(() => {
    if (!open) return;

    updateRightPanel({
      id: ownerId,
      kind,
      automatic,
      close: () => closeRef.current(),
      opener: openerRef.current,
      title,
      icon,
      panelId,
      registryKey,
      parentId,
    });
  }, [
    open,
    ownerId,
    kind,
    automatic,
    title,
    icon,
    panelId,
    registryKey,
    parentId,
  ]);

  return {
    ownerId,
    panelId,
    active: open && !!(flags & 1),
    hasPrevious: open && !!(flags & 1) && !!(flags & 2),
    openerRef,
  };
}

const FOCUSABLE =
  'a[href],button:not([disabled]),input:not([disabled]),select:not([disabled]),textarea:not([disabled]),[contenteditable="true"],[tabindex]:not([tabindex="-1"])';

function restoreOpenerFocus(openerRef: RefObject<HTMLElement | null>): void {
  requestAnimationFrame(() => {
    if (getRightPanelSnapshot().activeId || topmostVisibleModalDialog()) return;
    const active = document.activeElement;
    if (
      active instanceof HTMLElement &&
      active !== document.body &&
      active.isConnected &&
      !active.closest('[hidden],[inert],[aria-hidden="true"]')
    )
      return;
    const opener = openerRef.current;
    if (
      opener?.isConnected &&
      !opener.closest('[hidden],[inert],[aria-hidden="true"]')
    ) {
      opener.focus({ preventScroll: true });
      if (document.activeElement === opener) return;
    }
    const region = opener?.closest('[data-panel],main,[role="main"]');
    const page = region?.isConnected
      ? region
      : document.querySelector('main,[role="main"]');
    const visible = (element: HTMLElement) =>
      element.getClientRects().length > 0 &&
      !element.closest('[hidden],[inert],[aria-hidden="true"]');
    const selected = [
      ...(page?.querySelectorAll<HTMLElement>(
        'button[aria-pressed="true"],[role="tab"][aria-selected="true"]',
      ) ?? []),
    ].find(visible);
    const fallback =
      selected ??
      [...(page?.querySelectorAll<HTMLElement>(FOCUSABLE) ?? [])].find(visible);
    fallback?.focus({ preventScroll: true });
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
        const first =
          panel?.querySelector<HTMLElement>(
            '[role="tab"][aria-selected="true"]',
          ) ?? panel?.querySelector<HTMLElement>(FOCUSABLE);
        (first ?? panel)?.focus({ preventScroll: true });
      });
    }

    if (!open && wasOpen.current && !getRightPanelSnapshot().activeId) {
      restoreOpenerFocus(openerRef);
    }

    wasActive.current = active;
    wasOpen.current = open;
  }, [active, automatic, open, openerRef, panelRef]);

  useEffect(
    () => () => {
      if (!wasActive.current || getRightPanelSnapshot().activeId) return;
      restoreOpenerFocus(openerRef);
    },
    [openerRef],
  );

  useBodyScrollLock(active && presentation !== "docked", true);

  useEffect(() => {
    if (!active || presentation === "docked") return;

    const trapTab = (event: KeyboardEvent) => {
      if (event.key !== "Tab" || event.defaultPrevented) return;
      const panel = panelRef.current;
      if (!panel) return;
      // Same ownership rule as useDialogFocus: the panel keeps the Tab cycle
      // when the topmost visible dialog (modal or not) contains it.
      const top = topmostVisibleDialog();
      const topModal = topmostVisibleModalDialog();
      if (
        !(top?.contains(panel) || topModal?.contains(panel))
      )
        return;

      const focusable = [
        ...(panelRef.current?.querySelectorAll<HTMLElement>(FOCUSABLE) ?? []),
      ].filter(
        (element) =>
          element.getClientRects().length &&
          !element.closest('[hidden],[inert],[aria-hidden="true"]') &&
          (element.tabIndex >= 0 ||
            (element.matches('[contenteditable="true"]') &&
              !element.hasAttribute("tabindex"))),
      );
      if (focusable.length === 0) return;

      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      const panelHost =
        panelRef.current?.closest<HTMLElement>('[role="dialog"]') ?? null;
      if (document.activeElement === panelHost) {
        event.preventDefault();
        (event.shiftKey ? last : first).focus();
      } else if (event.shiftKey && document.activeElement === first) {
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
    };
  }, [active, presentation, panelRef]);
}
