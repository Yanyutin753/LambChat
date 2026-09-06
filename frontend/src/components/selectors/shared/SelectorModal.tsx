import type { ReactNode } from "react";
import { createPortal } from "react-dom";

interface SelectorModalPortalProps {
  open: boolean;
  onClose: () => void;
  children: ReactNode;
}

export function SelectorModalPortal({
  open,
  onClose,
  children,
}: SelectorModalPortalProps) {
  if (!open) return null;

  return createPortal(
    <>
      <div
        data-yields-sidebar
        className="fixed inset-0 z-[300] bg-black/50 animate-fade-in"
        onClick={onClose}
      />
      <div
        className="safe-area-x fixed z-[301] sm:inset-0 sm:flex sm:items-center sm:justify-center sm:p-4 inset-x-0 bottom-0 animate-slide-up sm:animate-scale-in"
        onClick={onClose}
      >
        {children}
      </div>
    </>,
    document.body,
  );
}
