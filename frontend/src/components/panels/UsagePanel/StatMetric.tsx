import type { LucideIcon } from "lucide-react";

export function StatMetric({
  icon: Icon,
  label,
  value,
  hint,
}: {
  icon: LucideIcon;
  label: string;
  value: string | number;
  hint?: string;
}) {
  return (
    <div className="group relative min-w-0 flex flex-col gap-2 border-r border-b border-[var(--usage-border)] px-3.5 py-4 transition-colors duration-200 hover:bg-[var(--usage-surface-hover)] sm:px-4 sm:py-5 xl:border-b-0">
      <div className="flex items-center gap-2 sm:gap-2.5">
        <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-md bg-[var(--usage-icon-bg)] text-[var(--theme-primary)] transition-colors duration-200 sm:h-8 sm:w-8">
          <Icon size={13} strokeWidth={2} />
        </div>
        <span className="min-w-0 truncate text-[10px] font-medium leading-none uppercase tracking-widest text-theme-text-tertiary sm:text-[11px]">
          {label}
        </span>
      </div>
      <p className="truncate pl-[2.25rem] text-xl font-black font-serif leading-none tracking-tight text-theme-text tabular-nums sm:pl-[2.5rem] sm:text-[1.45rem]">
        {value}
      </p>
      {hint && (
        <p className="truncate pl-[2.25rem] text-[10px] leading-snug text-theme-text-tertiary sm:pl-[2.5rem] sm:text-[11px]">
          <span className="text-theme-text-tertiary/50">&#x00B7;</span> {hint}
        </p>
      )}
    </div>
  );
}
