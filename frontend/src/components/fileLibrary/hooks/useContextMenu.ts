import { useState, useCallback, useRef, useId } from "react";
import type { RevealedFileItem } from "../../../services/api";

export function useContextMenu() {
  const [menu, setMenu] = useState<{
    x: number;
    y: number;
    file: RevealedFileItem;
  } | null>(null);
  const menuId = useId();
  const openerRef = useRef<HTMLElement | null>(null);

  const show = useCallback(
    (e: React.MouseEvent | React.KeyboardEvent, file: RevealedFileItem) => {
      e.preventDefault();
      e.stopPropagation();
      openerRef.current = e.currentTarget as HTMLElement;
      const rect = openerRef.current.getBoundingClientRect();
      const keyboard =
        e.type === "keydown" || (e.type === "click" && e.detail === 0);
      setMenu({
        x: keyboard || !("clientX" in e) ? rect.left : e.clientX,
        y: keyboard || !("clientY" in e) ? rect.bottom : e.clientY,
        file,
      });
    },
    [],
  );

  const hide = useCallback((restoreFocus = false) => {
    setMenu(null);
    if (restoreFocus) openerRef.current?.focus();
  }, []);

  return { menu, menuId, show, hide };
}
