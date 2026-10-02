import { AlertCircle } from "lucide-react";

interface ConfigPanelErrorCalloutProps {
  message: string;
  className?: string;
  tabIndex?: number;
}

export function ConfigPanelErrorCallout({
  message,
  className = "",
  tabIndex,
}: ConfigPanelErrorCalloutProps) {
  return (
    <div
      className={`glass-card flex items-start gap-2 rounded-xl p-3 text-14 text-red-600 !border-red-200/40 dark:text-red-400 dark:!border-red-800/30 focus-visible:outline-2 focus-visible:outline-[var(--theme-ring)] ${className}`}
      role="alert"
      tabIndex={tabIndex}
    >
      <AlertCircle size={18} className="mt-0.5 shrink-0" />
      <span className="min-w-0 [overflow-wrap:anywhere]">{message}</span>
    </div>
  );
}
