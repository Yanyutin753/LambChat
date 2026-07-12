import {
  Suspense,
  type ComponentType,
  type LazyExoticComponent,
  type ReactNode,
} from "react";
import type { CoreScheduledTaskSectionContribution } from "../../../extensions/coreContributions";

export interface ScheduledTaskSectionRendererProps {
  contribution: CoreScheduledTaskSectionContribution;
}

type ScheduledTaskSectionRendererComponent =
  ComponentType<ScheduledTaskSectionRendererProps>;
type ScheduledTaskSectionRenderer =
  | ScheduledTaskSectionRendererComponent
  | LazyExoticComponent<ScheduledTaskSectionRendererComponent>;

const SCHEDULED_TASK_SECTION_RENDERERS: Record<string, ScheduledTaskSectionRenderer> = {};

function MissingScheduledTaskSectionRenderer({
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

export function renderScheduledTaskSectionContribution(
  contribution: CoreScheduledTaskSectionContribution,
): ReactNode {
  const Renderer =
    SCHEDULED_TASK_SECTION_RENDERERS[contribution.renderer] ??
    MissingScheduledTaskSectionRenderer;
  return (
    <Suspense fallback={null}>
      <Renderer contribution={contribution} />
    </Suspense>
  );
}
