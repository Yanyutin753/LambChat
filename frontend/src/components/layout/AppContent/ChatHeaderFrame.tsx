import type { ReactNode } from "react";

export function ChatHeaderFrame({
  children,
  className = "",
}: {
  children: ReactNode;
  className?: string;
}) {
  return (
    <header
      className={
        "chat-header relative z-50 flex items-center px-3 sm:px-5 py-3 -mb-2 max-sm:h-12 max-sm:py-0 max-sm:mb-0 shrink-0 rounded-bl-xl after:pointer-events-none after:absolute after:inset-x-0 after:bottom-0 after:h-2 after:bg-[linear-gradient(to_bottom,var(--theme-bg),transparent)] " +
        className
      }
    >
      {children}
    </header>
  );
}
