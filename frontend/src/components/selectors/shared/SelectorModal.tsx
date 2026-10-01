import type { ReactNode } from "react";
import { ModalSurface } from "../../common/ModalSurface";

export function SelectorModalPortal({
  open,
  onClose,
  children,
}: {
  open: boolean;
  onClose: () => void;
  children: ReactNode;
}) {
  return (
    <ModalSurface open={open} onClose={onClose}>
      {children}
    </ModalSurface>
  );
}
