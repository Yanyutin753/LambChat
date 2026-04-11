import { useState, useCallback, useRef, useEffect } from "react";
import type { RevealedFileItem } from "../../../services/api";

export function useContextMenu() {
  const [menu, setMenu] = useState<{
    x: number;
    y: number;
    file: RevealedFileItem;
  } | null>(null);
  const menuRef = useRef<HTMLDivElement>(null);

  const show = useCallback((e: React.MouseEvent, file: RevealedFileItem) => {
    e.preventDefault();
    e.stopPropagation();
    setMenu({ x: e.clientX, y: e.clientY, file });
  }, []);

  const hide = useCallback(() => setMenu(null), []);

  // Close on click outside
  useEffect(() => {
    if (!menu) return;
    const handler = () => hide();
    document.addEventListener("click", handler);
    return () => document.removeEventListener("click", handler);
  }, [menu, hide]);

  // Reposition if overflowing viewport
  useEffect(() => {
    if (!menu || !menuRef.current) return;
    const rect = menuRef.current.getBoundingClientRect();
    const el = menuRef.current;
    if (rect.right > window.innerWidth)
      el.style.left = `${window.innerWidth - rect.width - 8}px`;
    if (rect.bottom > window.innerHeight)
      el.style.top = `${window.innerHeight - rect.height - 8}px`;
  }, [menu]);

  return { menu, menuRef, show, hide };
}
