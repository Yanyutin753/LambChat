import type { ReactNode } from "react";
import clsx from "clsx";
import "./viewer.css";

interface ViewerTopBarProps {
  children: ReactNode;
  className?: string;
  contentClassName?: string;
}

export function ViewerTopBar({
  children,
  className,
  contentClassName,
}: ViewerTopBarProps) {
  return (
    <div
      className={clsx(
        "viewer-top-bar safe-area-top pointer-events-none absolute inset-x-0 top-0 z-20 safe-area-x",
        className,
      )}
    >
      <div
        className={clsx(
          "flex h-14 items-center justify-between px-3 sm:px-6",
          contentClassName,
        )}
      >
        {children}
      </div>
    </div>
  );
}
