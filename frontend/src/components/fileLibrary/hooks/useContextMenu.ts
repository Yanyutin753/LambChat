import {
  useState,
  useCallback,
  useRef,
  useEffect,
  useLayoutEffect,
} from "react";
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
  useLayoutEffect(() => {
    if (!menu || !menuRef.current) return;
    const rect = menuRef.current.getBoundingClientRect();
    const el = menuRef.current;
    el.style.left = `${Math.max(
      8,
      Math.min(menu.x, window.innerWidth - rect.width - 8),
    )}px`;
    el.style.top = `${Math.max(
      8,
      Math.min(menu.y, window.innerHeight - rect.height - 8),
    )}px`;
  }, [menu]);

  return { menu, menuRef, show, hide };
}
