import { useLayoutEffect, useRef, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";

export interface ResourceCardAction {
  label: string;
  icon?: ReactNode;
  onClick: () => void;
  danger?: boolean;
}

interface ResourceCardMenuProps {
  id: string;
  title: string;
  actions: ResourceCardAction[];
  position: { x: number; y: number };
  onClose: (restoreFocus?: boolean) => void;
}

export function ResourceCardMenu({
  id,
  title,
  actions,
  position,
  onClose,
}: ResourceCardMenuProps) {
  const ref = useRef<HTMLDivElement>(null);
  const [fitted, setFitted] = useState(position);
  useLayoutEffect(() => {
    const menu = ref.current!;
    const rect = menu.getBoundingClientRect();
    const viewport = window.visualViewport;
    const left = viewport?.offsetLeft ?? 0;
    const top = viewport?.offsetTop ?? 0;
    setFitted({
      x: Math.max(
        left + 8,
        Math.min(
          position.x,
          left + (viewport?.width ?? window.innerWidth) - rect.width - 8,
        ),
      ),
      y: Math.max(
        top + 8,
        Math.min(
          position.y,
          top + (viewport?.height ?? window.innerHeight) - rect.height - 8,
        ),
      ),
    });
    menu.querySelector<HTMLButtonElement>("button")?.focus();
    const outside = (event: PointerEvent) => {
      const trigger = (event.target as Element).closest?.(
        '[aria-haspopup="menu"]',
      );
      if (
        !menu.contains(event.target as Node) &&
        trigger?.getAttribute("aria-controls") !== id
      )
        onClose();
    };
    const dismiss = (event: KeyboardEvent) => {
      if (event.key === "Escape" || event.key === "Tab") {
        if (event.key === "Escape") event.preventDefault();
        onClose(true);
      }
    };
    const reposition = (event: Event) => {
      if (!menu.contains(event.target as Node)) onClose();
    };
    document.addEventListener("pointerdown", outside);
    document.addEventListener("keydown", dismiss, true);
    window.addEventListener("resize", reposition);
    window.addEventListener("scroll", reposition, true);
    viewport?.addEventListener("resize", reposition);
    viewport?.addEventListener("scroll", reposition);
    return () => {
      document.removeEventListener("pointerdown", outside);
      document.removeEventListener("keydown", dismiss, true);
      window.removeEventListener("resize", reposition);
      window.removeEventListener("scroll", reposition, true);
      viewport?.removeEventListener("resize", reposition);
      viewport?.removeEventListener("scroll", reposition);
    };
  }, [position, onClose, id]);

  return createPortal(
    <div
      ref={ref}
      id={id}
      role="menu"
      aria-label={title}
      className="fixed z-[999] w-56 max-w-[calc(100vw-16px)] max-h-[calc(100dvh-16px)] overflow-auto rounded-xl border border-theme-border bg-theme-bg-card p-1 shadow-xl"
      style={{ left: fitted.x, top: fitted.y }}
      onClick={(event) => event.stopPropagation()}
      onContextMenu={(event) => {
        event.preventDefault();
        event.stopPropagation();
      }}
      onKeyDown={(event) => {
        event.stopPropagation();
        const buttons = Array.from(
          ref.current!.querySelectorAll<HTMLButtonElement>("button"),
        );
        const index = buttons.indexOf(
          document.activeElement as HTMLButtonElement,
        );
        const next =
          event.key === "ArrowDown"
            ? (index + 1) % buttons.length
            : event.key === "ArrowUp"
              ? (index - 1 + buttons.length) % buttons.length
              : event.key === "Home"
                ? 0
                : event.key === "End"
                  ? buttons.length - 1
                  : -1;
        if (next >= 0) {
          event.preventDefault();
          buttons[next].focus();
        }
      }}
    >
      {actions.map((action) => (
        <button
          key={action.label}
          type="button"
          role="menuitem"
          tabIndex={-1}
          className={`flex min-h-11 w-full items-center gap-2 rounded-lg px-3 py-2 text-left text-13 focus-visible:outline focus-visible:outline-2 focus-visible:outline-[var(--theme-primary)] ${action.danger ? "text-theme-error hover:bg-[color-mix(in_srgb,var(--theme-error)_10%,transparent)]" : "text-theme-text hover:bg-theme-bg-subtle"}`}
          onClick={() => {
            onClose(true);
            action.onClick();
          }}
        >
          {action.icon}
          <span className="min-w-0 break-words">{action.label}</span>
        </button>
      ))}
    </div>,
    document.body,
  );
}
