import { SkeletonLine } from "./primitives";
import { PanelHeaderSkeleton } from "./PanelHeaderSkeleton";
import {
  PANEL_ROW_SKELETON_COUNT,
  PanelSegmentedTabsSkeleton,
} from "./PanelSkeletonHelpers";

function AgentListSkeletonRows({
  withCheckbox = false,
}: {
  withCheckbox?: boolean;
}) {
  return (
    <div className="glass-card divide-y divide-[var(--glass-border)] overflow-hidden rounded-xl">
      {Array.from({ length: PANEL_ROW_SKELETON_COUNT }).map((_, i) => (
        <div
          key={i}
          className="flex items-center justify-between gap-3 font-serif px-4 py-3.5"
        >
          <div className="flex min-w-0 flex-1 items-center gap-3.5">
            {withCheckbox && (
              <div className="skeleton-line size-4 rounded shrink-0" />
            )}
            <div className="flex size-10 shrink-0 items-center justify-center rounded-xl ring-1 ring-[var(--glass-border)]">
              <div className="skeleton-line size-5 rounded-md" />
            </div>
            <div className="min-w-0 flex-1">
              <SkeletonLine
                width={i % 2 === 0 ? "w-20 sm:w-28" : "w-28 sm:w-36"}
                className="!h-[13px] sm:!h-[14px]"
              />
              <SkeletonLine
                width="w-3/5"
                className="!h-2.5 sm:!h-3 mt-1 hidden sm:block"
              />
            </div>
          </div>
          {!withCheckbox && (
            <div className="skeleton-line h-5 w-10 rounded-full shrink-0" />
          )}
        </div>
      ))}
    </div>
  );
}

function ModelRowsSkeleton({ compact = false }: { compact?: boolean }) {
  return (
    <div className={compact ? "space-y-3" : "space-y-3"}>
      {Array.from({ length: PANEL_ROW_SKELETON_COUNT }).map((_, i) => (
        <div key={i} className="glass-card rounded-xl">
          <div className="block p-3.5 sm:hidden">
            <div className="mb-2 flex items-center justify-between gap-2">
              <div className="flex min-w-0 flex-1 items-center gap-2">
                <div className="skeleton-line size-4 rounded shrink-0 !opacity-30" />
                <div className="skeleton-line size-5 rounded shrink-0" />
                <SkeletonLine
                  width={i % 2 === 0 ? "w-24" : "w-20"}
                  className="!h-[13px] flex-1"
                />
              </div>
              <div className="skeleton-line h-5 w-10 rounded-full shrink-0" />
            </div>
            <SkeletonLine width="w-32" className="!h-3 !opacity-60" />
            <div className="mt-2 flex items-center justify-end gap-1">
              <div className="skeleton-line size-8 rounded-lg" />
              <div className="skeleton-line size-8 rounded-lg" />
              <div className="skeleton-line size-8 rounded-lg" />
            </div>
          </div>

          <div className="hidden items-center justify-between gap-2 p-4 sm:flex">
            <div className="flex min-w-0 flex-1 items-center gap-3">
              <div className="skeleton-line size-4 rounded shrink-0 !opacity-30" />
              <div className="skeleton-line size-5 rounded shrink-0" />
              <div className="min-w-0 flex-1">
                <SkeletonLine
                  width={i % 2 === 0 ? "w-24 sm:w-32" : "w-20 sm:w-28"}
                  className="!h-[13px] sm:!h-[14px]"
                />
                <SkeletonLine width="w-40" className="!h-3 mt-1 !opacity-60" />
              </div>
            </div>
            <div className="flex shrink-0 items-center gap-1.5">
              <div className="skeleton-line h-5 w-10 rounded-full" />
              <div className="skeleton-line size-8 rounded-lg" />
              <div className="skeleton-line size-8 rounded-lg" />
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}

export function AgentSectionSkeleton() {
  return (
    <div className="panel-body panel-stack animate-glass-enter">
      <PanelSegmentedTabsSkeleton
        activeWidth="w-16 sm:w-20"
        inactiveWidth="w-12 sm:w-16"
      />
      <div className="space-y-4">
        <SkeletonLine
          width="w-3/4"
          className="!h-3 !opacity-60 hidden sm:block"
        />
        <AgentListSkeletonRows />
      </div>
    </div>
  );
}

export function ModelSectionSkeleton() {
  return (
    <div className="panel-body panel-stack animate-glass-enter">
      <PanelSegmentedTabsSkeleton
        activeWidth="w-14 sm:w-16"
        inactiveWidth="w-20 sm:w-28"
      />
      <div className="space-y-4">
        <SkeletonLine
          width="w-48"
          className="!h-3.5 !opacity-60 hidden sm:block"
        />
        <div className="skeleton-line h-10 w-full max-w-xs rounded-lg" />
        <div className="agent-config-list overflow-hidden rounded-lg border border-[var(--glass-border)] bg-[var(--glass-bg)] divide-y divide-[var(--glass-border)]">
          <div className="flex items-center justify-between gap-3 font-serif bg-[var(--glass-bg-subtle)] px-3.5 py-2.5 sm:px-4">
            <SkeletonLine width="w-36 sm:w-48" className="!h-3" />
            <div className="flex items-center gap-2">
              <SkeletonLine width="w-10" className="!h-3" />
              <SkeletonLine width="w-10" className="!h-3" />
            </div>
          </div>
          <div className="px-3.5 py-2 sm:px-4">
            <SkeletonLine width="w-28" className="!h-6 !rounded-full" />
          </div>
          {Array.from({ length: PANEL_ROW_SKELETON_COUNT }).map((_, i) => (
            <div
              key={i}
              className="flex min-h-14 items-center gap-3 px-3.5 py-3 sm:px-4 sm:gap-3.5"
            >
              <div className="skeleton-line size-4 rounded shrink-0" />
              <div className="skeleton-line size-5 rounded shrink-0" />
              <div className="min-w-0 flex-1">
                <SkeletonLine
                  width={i % 2 === 0 ? "w-24" : "w-28"}
                  className="!h-3.5"
                />
                <SkeletonLine
                  width="w-32"
                  className="!h-3 mt-1 sm:hidden !opacity-60"
                />
              </div>
              <SkeletonLine
                width="w-28"
                className="!h-3 hidden sm:block !opacity-60"
              />
              <div className="skeleton-line size-5 rounded shrink-0" />
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

export function AgentModelPanelSkeleton() {
  return (
    <div className="glass-shell flex h-full flex-col min-h-0 animate-fade-in">
      <PanelHeaderSkeleton
        hasSearch={false}
        hasSubtitle
        className="panel-header--section-switch"
        actions={
          <div className="agent-model-section-switcher inline-grid grid-cols-2 rounded-lg border border-[var(--glass-border)] bg-[var(--glass-bg-subtle)] p-1 font-serif">
            {[0, 1].map((tab) => (
              <div
                key={tab}
                className="flex items-center justify-center gap-2 rounded-md px-3 py-2"
              >
                <div className="skeleton-line size-4 rounded" />
                <SkeletonLine width="w-16" className="!h-4" />
              </div>
            ))}
          </div>
        }
      />
      <div className="panel-scroll min-h-0 flex-1 overflow-y-auto">
        <AgentSectionSkeleton />
      </div>
    </div>
  );
}

/** Agent panel: single divided container with tab switcher */
export function AgentPanelSkeleton() {
  return (
    <div className="glass-shell flex h-full flex-col min-h-0 animate-fade-in">
      <PanelHeaderSkeleton hasSearch={false} hasSubtitle />
      {/* Tab bar — segmented control */}
      <PanelSegmentedTabsSkeleton
        activeWidth="w-16 sm:w-20"
        inactiveWidth="w-12 sm:w-16"
      />
      {/* Description text */}
      <div className="px-4 sm:px-6">
        <SkeletonLine
          width="w-3/4"
          className="!h-3 !opacity-60 hidden sm:block"
        />
      </div>
      {/* Agent list — plain container with divide-y (matches real layout) */}
      <div className="panel-body flex-1 min-h-0 overflow-y-auto">
        <AgentListSkeletonRows />
      </div>
    </div>
  );
}

/** Model panel: model config rows with tab switcher */
export function ModelPanelSkeleton() {
  return (
    <div className="glass-shell flex h-full flex-col min-h-0 animate-fade-in">
      <PanelHeaderSkeleton hasSearch={false} hasSubtitle />
      {/* Tab bar — segmented control */}
      <PanelSegmentedTabsSkeleton
        activeWidth="w-14 sm:w-16"
        inactiveWidth="w-20 sm:w-28"
      />
      <div className="panel-body flex-1 min-h-0 overflow-y-auto">
        {/* Toolbar — description text + action buttons on right */}
        <div className="flex items-center justify-between gap-3 font-serif">
          <SkeletonLine
            width="w-48"
            className="!h-3.5 !opacity-60 hidden sm:block"
          />
          <div className="flex items-center gap-1.5 sm:gap-2 ml-auto">
            <div className="skeleton-line h-8 w-16 sm:w-20 rounded-lg" />
            <div className="skeleton-line h-8 w-16 sm:w-20 rounded-lg hidden sm:block" />
            <div className="skeleton-line h-8 w-16 sm:w-20 rounded-lg hidden sm:block" />
            <div className="skeleton-line h-8 w-16 sm:w-20 rounded-lg" />
          </div>
        </div>
        <ModelRowsSkeleton />
      </div>
    </div>
  );
}

export function SettingsPanelSkeleton() {
  return (
    <div
      className="glass-shell flex h-full min-h-0 flex-col sm:flex-row"
      aria-hidden="true"
    >
      <div className="settings-sidebar hidden w-60 shrink-0 flex-col border-r border-[var(--glass-border)] sm:flex">
        <div className="flex items-center gap-2.5 px-5 py-4">
          <div className="skeleton-line size-12 shrink-0 rounded-lg" />
          <div className="min-w-0 flex-1">
            <SkeletonLine width="w-20" className="!h-4" />
            <SkeletonLine width="w-28" className="mt-2 !h-3" />
          </div>
        </div>
        <div className="panel-stack p-3">
          {Array.from({ length: 9 }).map((_, i) => (
            <div key={i} className="flex items-center gap-3 p-3">
              <div className="skeleton-line size-4 rounded" />
              <SkeletonLine width="w-28" />
            </div>
          ))}
        </div>
      </div>
      <div className="settings-content flex min-w-0 flex-1 flex-col overflow-hidden">
        <div className="settings-toolbar panel-inset shrink-0">
          <div className="settings-compact-identity mb-3 items-center gap-3">
            <div className="skeleton-line size-12 rounded-lg" />
            <SkeletonLine width="w-24" className="!h-4" />
          </div>
          <div className="settings-category-picker block sm:hidden mb-3">
            <SkeletonLine width="w-16" className="mb-1" />
            <div className="skeleton-line h-11 w-full rounded-lg" />
          </div>
          <div className="flex items-center gap-2">
            <div className="skeleton-line h-10 min-w-0 flex-1 rounded-lg" />
            <div className="skeleton-line size-10 rounded-lg" />
            <div className="skeleton-line size-10 rounded-lg" />
          </div>
        </div>
        <div className="panel-body min-h-0 flex-1 overflow-y-auto">
          <div className="mb-6">
            <SkeletonLine width="w-20" />
            <SkeletonLine width="w-40" className="!h-[18px] mt-2" />
          </div>
          <SettingsListSkeleton />
        </div>
      </div>
    </div>
  );
}

export function SettingsListSkeleton() {
  return (
    <div className="panel-sections">
      {[0, 1, 2].map((section) => (
        <div key={section} className="panel-stack">
          <SkeletonLine width="w-28" className="!h-4" />
          {[0, 1].map((row) => (
            <div key={row} className="glass-card rounded-xl p-4">
              <SkeletonLine width="w-1/3" className="!h-4" />
              <SkeletonLine width="w-2/3" className="mt-2 !opacity-60" />
              <div className="skeleton-line h-10 w-full rounded-lg mt-3" />
            </div>
          ))}
        </div>
      ))}
    </div>
  );
}
