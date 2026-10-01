import { useState, useCallback, useId, useRef } from "react";
import type { RevealedFileItem } from "../../../services/api";

export function useContextMenu() {
  const [menu, setMenu] = useState<{
    x: number;
    y: number;
    file: RevealedFileItem;
  } | null>(null);
  const menuId = useId();
  const focusReturn = useRef<HTMLElement | null>(null);

  const show = useCallback((e: React.MouseEvent, file: RevealedFileItem) => {
    e.preventDefault();
    e.stopPropagation();
    focusReturn.current =
      (e.target as Element).closest<HTMLElement>("button") ??
      e.currentTarget.querySelector<HTMLElement>("button");
    const rect = e.currentTarget.getBoundingClientRect();
    setMenu({
      x: e.detail === 0 && e.type !== "contextmenu" ? rect.left : e.clientX,
      y: e.detail === 0 && e.type !== "contextmenu" ? rect.bottom : e.clientY,
      file,
    });
  }, []);

  const hide = useCallback((restoreFocus = false) => {
    setMenu(null);
    if (restoreFocus) focusReturn.current?.focus();
  }, []);

  return { menu, menuId, show, hide };
}
