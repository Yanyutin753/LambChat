import {
  Suspense,
  type ComponentType,
  type LazyExoticComponent,
  type ReactNode,
} from "react";
import type { CoreScheduledTaskSectionContribution } from "../../../extensions/coreContributions";
import {
  MissingScheduledTaskSectionRenderer,
  type ScheduledTaskSectionRendererProps,
} from "./scheduledTaskSectionRendererComponents";

type ScheduledTaskSectionRendererComponent =
  ComponentType<ScheduledTaskSectionRendererProps>;
type ScheduledTaskSectionRenderer =
  | ScheduledTaskSectionRendererComponent
  | LazyExoticComponent<ScheduledTaskSectionRendererComponent>;

const SCHEDULED_TASK_SECTION_RENDERERS: Record<string, ScheduledTaskSectionRenderer> = {};

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

export type { ScheduledTaskSectionRendererProps };
