import React from "react";

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
    ? { position: "fixed", top: pos.top, left: 8, right: 8, zIndex: 50 }
    : {
        position: "fixed",
        top: pos.top,
        [align]: align === "left" ? pos.left : pos.right,
        zIndex: 50,
      };

  return (
    <>
      {/* Backdrop */}
      <div className="fixed inset-0 z-[1]" onClick={onClose} />

      {/* Menu */}
      <div
        className={`
          py-1.5 ${isMobile ? "w-auto" : w} ${maxH ?? ""}
          rounded-xl
          border border-stone-200/80 dark:border-stone-700/60
          bg-white dark:bg-stone-800
          shadow-xl shadow-stone-900/[0.06] dark:shadow-black/40
          ${maxH ? "overflow-y-auto scrollbar-none" : ""}
          animate-in fade-in-0 zoom-in-95 duration-100
        `}
        style={positionStyle}
      >
        {children}
      </div>
    </>
  );
}
