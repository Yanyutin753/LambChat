import type { ReactNode } from "react";
import { ModalSurface } from "../../common/ModalSurface";

export function SelectorModalPortal({
  open,
  onClose,
  children,
  className,
}: {
  open: boolean;
  onClose: () => void;
  children: ReactNode;
  className?: string;
}) {
  return (
    <ModalSurface open={open} onClose={onClose} className={className}>
      {children}
    </ModalSurface>
  );
}
