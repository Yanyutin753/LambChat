import type { CoreScheduledTaskSectionContribution } from "../../../extensions/coreContributions";

export interface ScheduledTaskSectionRendererProps {
  contribution: CoreScheduledTaskSectionContribution;
}

export function MissingScheduledTaskSectionRenderer({
  contribution,
}: ScheduledTaskSectionRendererProps) {
  return (
    <section className="border-b border-[var(--glass-border)] px-4 py-3 sm:px-6">
      <div className="rounded-lg border border-dashed border-[var(--glass-border)] px-3 py-3 text-xs text-[var(--theme-text-secondary)]">
        Plugin scheduled task section renderer is not registered:
        <span className="ml-1 font-mono">{contribution.renderer}</span>
      </div>
    </section>
  );
}
