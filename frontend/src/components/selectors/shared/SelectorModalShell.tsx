import { forwardRef, type CSSProperties, type HTMLAttributes } from "react";

export const SELECTOR_MODAL_SHELL_CLASS =
  "sm:rounded-[28px] rounded-t-[28px] w-full sm:w-[min(760px,calc(100vw-2rem))] min-h-[40vh] sm:max-h-[82vh] max-h-[88vh] max-h-[88dvh] flex flex-col overflow-hidden border border-white/70 dark:border-stone-700/80 shadow-[0_24px_80px_rgba(15,23,42,0.22)] dark:shadow-[0_24px_80px_rgba(0,0,0,0.45)]";

interface SelectorModalShellProps extends HTMLAttributes<HTMLDivElement> {
  style?: CSSProperties;
}

function cx(...classes: Array<string | false | null | undefined>): string {
  return classes.filter(Boolean).join(" ");
}

export const SelectorModalShell = forwardRef<
  HTMLDivElement,
  SelectorModalShellProps
>(function SelectorModalShell({ className, style, children, ...props }, ref) {
  return (
    <div
      ref={ref}
      className={cx(SELECTOR_MODAL_SHELL_CLASS, className)}
      style={{ background: "var(--theme-bg-card)", ...style }}
      onClick={(event) => event.stopPropagation()}
      {...props}
    >
      {children}
    </div>
  );
});
