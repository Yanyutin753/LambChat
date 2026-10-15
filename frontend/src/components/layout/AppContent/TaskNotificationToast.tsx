import { ToastDismissButton } from "../../common/ToastDismissButton";
interface TaskNotificationToastProps {
  visible: boolean;
  title: string;
  body: string;
  openLabel: string;
  dismissLabel: string;
  onOpen: () => void;
  onDismiss: () => void;
}
export function TaskNotificationToast({ visible, title, body, openLabel, dismissLabel, onOpen, onDismiss }: TaskNotificationToastProps) {
  return <div className={`pointer-events-auto flex w-full max-w-[min(92vw,24rem)] items-start rounded-xl border border-theme-border bg-theme-bg-card p-2 text-theme-text shadow-lg transition-[opacity,transform] motion-reduce:transition-none ${visible ? "translate-y-0 opacity-100" : "translate-y-1.5 opacity-0"}`}>
    <div className="min-w-0 flex-1 px-2 pt-1.5">
      <span role="status" aria-live="polite" aria-atomic="true">
        <span className="line-clamp-1 block text-13 font-semibold leading-tight">{title}</span>
        <span className="mt-1 line-clamp-2 block text-12 leading-snug text-theme-text-secondary">{body}</span>
      </span>
      <button type="button" onClick={onOpen} aria-label={`${openLabel}: ${title}`}
        className="min-h-11 max-w-full rounded-lg text-left text-12 text-theme-primary underline underline-offset-4 focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-theme-primary">
        {openLabel}
      </button>
    </div>
    <ToastDismissButton label={dismissLabel} onDismiss={onDismiss} />
  </div>;
}
