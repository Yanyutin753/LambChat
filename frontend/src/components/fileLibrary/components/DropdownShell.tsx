import React from "react";
import { createPortal } from "react-dom";

interface DropdownShellProps {
  show: boolean;
  onClose: () => void;
  pos: { top: number; left: number; right: number } | null;
  align: "left" | "right";
  w: string;
  maxH?: string;
  children: React.ReactNode;
}

export function DropdownShell({
  show,
  onClose,
  pos,
  align,
  w,
  maxH,
  children,
}: DropdownShellProps) {
  if (!show || !pos) return null;

  const isMobile = window.innerWidth < 640;

  const positionStyle: React.CSSProperties = isMobile
    ? { position: "fixed", top: pos.top, left: 8, right: 8, zIndex: 999 }
    : {
        position: "fixed",
        top: pos.top,
        [align]: align === "left" ? pos.left : pos.right,
        zIndex: 999,
      };

  return createPortal(
    <>
      {/* Backdrop */}
      <div className="fixed inset-0 z-[998]" onClick={onClose} />

      {/* Menu */}
      <div
        className={`
          py-1.5 ${isMobile ? "w-auto" : w} ${maxH ?? ""}
          rounded-xl
          border border-theme-border
          bg-theme-bg-card
          shadow-xl
          ${maxH ? "overflow-y-auto scrollbar-none" : ""}
          animate-in fade-in-0 zoom-in-95 duration-100
        `}
        style={positionStyle}
      >
        {children}
      </div>
    </>,
    document.body,
  );
}
