import {
  useEffect,
  useRef,
  type CSSProperties,
  type KeyboardEvent,
  type RefObject,
} from "react";
import { useStickyDropdownPosition } from "./useStickyDropdownPosition";
import { restoreOpenerFocusUnclaimed } from "../utils/modalDialog";

const DROPDOWN_GUTTER = 12;

function getViewportBounds() {
  const visualViewport = window.visualViewport;
  return {
    width: visualViewport?.width ?? window.innerWidth,
    height: visualViewport?.height ?? window.innerHeight,
    offsetTop: visualViewport?.offsetTop ?? 0,
    offsetLeft: visualViewport?.offsetLeft ?? 0,
  };
}

function getDropdownPosition(rect: DOMRect, width: number): CSSProperties {
  const viewport = getViewportBounds();
  const availableWidth = viewport.width - DROPDOWN_GUTTER * 2;
  const renderedWidth = Math.min(width, availableWidth);
  const minLeft = viewport.offsetLeft + DROPDOWN_GUTTER;
  const maxLeft =
    viewport.offsetLeft + viewport.width - renderedWidth - DROPDOWN_GUTTER;
  const left = Math.min(Math.max(minLeft, rect.right - renderedWidth), maxLeft);
  const below =
    viewport.offsetTop + viewport.height - rect.bottom - 8 - DROPDOWN_GUTTER;
  const above = rect.top - viewport.offsetTop - 8 - DROPDOWN_GUTTER;
  const preferBelow = below >= 160 || below >= above;

  return {
    top: preferBelow ? rect.bottom + 8 : undefined,
    bottom: preferBelow ? undefined : window.innerHeight - rect.top + 8,
    left,
    width: renderedWidth,
    maxHeight: Math.max(0, preferBelow ? below : above),
  };
}

/** Shared placement and keyboard ownership for the existing panel filters. */
export function usePanelFilterMenu(
  triggerRef: RefObject<HTMLButtonElement | null>,
  isOpen: boolean,
  width: number,
  onClose: () => void,
) {
  const menuRef = useRef<HTMLDivElement | null>(null);
  const dropdownStyle = useStickyDropdownPosition(triggerRef, isOpen, (rect) =>
    getDropdownPosition(rect, width),
  );
  const ready = isOpen && Object.keys(dropdownStyle).length > 0;
  useEffect(() => {
    if (!ready) return;
    const menu = menuRef.current;
    const trigger = triggerRef.current;
    (
      menu?.querySelector<HTMLButtonElement>('[aria-checked="true"]') ??
      menu?.querySelector<HTMLButtonElement>("button") ??
      menu
    )?.focus();
    return () => {
      if (menu?.contains(document.activeElement))
        queueMicrotask(() => restoreOpenerFocusUnclaimed(trigger, menu));
    };
  }, [ready, triggerRef]);

  const closeMenu = () => {
    restoreOpenerFocusUnclaimed(triggerRef.current, menuRef.current);
    onClose();
  };

  const onKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    if (
      event.defaultPrevented ||
      event.nativeEvent.isComposing ||
      event.keyCode === 229
    )
      return;
    event.stopPropagation();
    if (event.key === "Escape" || event.key === "Tab") {
      if (event.key === "Escape") event.preventDefault();
      closeMenu();
      return;
    }
    const items = Array.from(
      menuRef.current?.querySelectorAll<HTMLButtonElement>(
        "button:not(:disabled)",
      ) ?? [],
    );
    if (!items.length) return;
    const index = items.indexOf(document.activeElement as HTMLButtonElement);
    const next =
      event.key === "ArrowDown"
        ? (index + 1) % items.length
        : event.key === "ArrowUp"
          ? index <= 0
            ? items.length - 1
            : index - 1
          : event.key === "Home"
            ? 0
            : event.key === "End"
              ? items.length - 1
              : -1;
    if (next >= 0) {
      event.preventDefault();
      items[next].focus();
    }
  };
  return { menuRef, dropdownStyle, ready, onKeyDown, closeMenu };
}
