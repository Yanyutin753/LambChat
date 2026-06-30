import { SkeletonLine } from "./primitives";
import { PanelHeaderSkeleton } from "./PanelHeaderSkeleton";
import {
  PANEL_CARD_SKELETON_COUNT,
  PanelPaginationSkeleton,
} from "./PanelSkeletonHelpers";

/** MCP panel: card grid matching real MCPServerCard (pps-card) structure */
export function MCPPanelSkeleton() {
  return (
    <div className="glass-shell flex h-full flex-col min-h-0 animate-fade-in">
      <PanelHeaderSkeleton />
      <div className="flex-1 overflow-y-auto py-2 sm:py-4 px-4">
        <div className="grid auto-grid-cols gap-3">
          {Array.from({ length: PANEL_CARD_SKELETON_COUNT }).map((_, i) => (
            <div
              key={i}
              className="pps-card group flex h-full flex-col overflow-hidden rounded-xl border border-[var(--theme-border)] bg-[var(--theme-bg-card)] shadow-sm"
            >
              {/* Banner */}
              <div
                className="pps-card__banner relative h-12 shrink-0"
                style={{
                  background: `linear-gradient(135deg, ${
                    [
                      "var(--theme-primary-light)",
                      "color-mix(in srgb, var(--theme-primary-light) 60%, var(--theme-bg))",
                      "var(--theme-bg-card)",
                    ][i % 3]
                  }, var(--theme-bg-card))`,
                }}
              >
                {/* Status badges on banner */}
                <div className="absolute bottom-1.5 left-3 flex gap-1">
                  <SkeletonLine
                    width="w-10 sm:w-12"
                    className="!h-3.5 !rounded-full"
                  />
                  <SkeletonLine
                    width="w-8 sm:w-10"
                    className="!h-3.5 !rounded-full"
                  />
                </div>
              </div>
              {/* Card body */}
              <div className="flex flex-1 flex-col -mt-3 pt-5 p-3">
                <div className="flex items-start gap-2.5">
                  <div className="scb__icon-ring shrink-0 skeleton-line" />
                  <div className="min-w-0 flex-1">
                    <SkeletonLine
                      width={i % 2 === 0 ? "w-24 sm:w-36" : "w-20 sm:w-28"}
                      className="!h-[15px] sm:!h-[16px]"
                    />
                    {/* Transport badge */}
                    <SkeletonLine
                      width="w-10 sm:w-12"
                      className="!h-3.5 !rounded-full mt-1"
                    />
                  </div>
                </div>
                {/* URL/command */}
                <div className="mt-2">
                  <SkeletonLine width="w-3/5" className="!h-3 !rounded-md" />
                </div>
                <div className="flex-1" />
              </div>
              {/* Footer */}
              <div className="flex items-center justify-between px-3 py-2 border-t border-[var(--theme-border)]">
                <div className="flex items-center gap-1.5">
                  <div className="skeleton-line size-7 rounded-lg" />
                  <div className="skeleton-line size-7 rounded-lg" />
                </div>
                <div className="skeleton-line w-10 sm:w-12 h-5 !rounded-full" />
              </div>
            </div>
          ))}
        </div>
        {/* Pagination placeholder */}
        <PanelPaginationSkeleton />
      </div>
    </div>
  );
}

/** Feedback panel: stats cards + feedback items */
export function FeedbackPanelSkeleton() {
  return (
    <div className="glass-shell flex h-full flex-col min-h-0 animate-fade-in">
      <PanelHeaderSkeleton hasSearch={false} />

      {/* Stats section */}
      <div className="grid grid-cols-2 gap-3 px-4 sm:grid-cols-4 sm:gap-4 sm:px-6">
        {[0, 1, 2, 3].map((i) => (
          <div key={i} className="glass-card rounded-xl p-4">
            <div className="flex items-center gap-2 sm:gap-3">
              <div
                className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg"
                style={{
                  backgroundColor:
                    "var(--glass-bg-subtle, color-mix(in srgb, var(--theme-bg) 80%, white))",
                }}
              >
                <div className="skeleton-line size-6 rounded-md" />
              </div>
              <div className="min-w-0">
                <SkeletonLine width="w-10 sm:w-12" className="!h-2.5 sm:!h-3" />
                <SkeletonLine
                  width="w-6 sm:w-8"
                  className="!h-5 sm:!h-6 mt-1"
                />
              </div>
            </div>
          </div>
        ))}
      </div>

      {/* Feedback list */}
      <div className="flex-1 overflow-y-auto py-2 sm:py-4 px-4 sm:px-6">
        {/* Desktop */}
        <div className="hidden space-y-3 sm:block">
          {Array.from({ length: 7 }).map((_, i) => (
            <div key={i} className="glass-card rounded-xl p-5">
              <div className="flex items-center justify-between gap-2">
                <div className="flex items-center gap-2 sm:gap-3 min-w-0">
                  <div className="skeleton-line size-9 sm:size-10 rounded-full shrink-0" />
                  <div className="min-w-0">
                    <SkeletonLine
                      width={i % 2 === 0 ? "w-16 sm:w-20" : "w-20 sm:w-24"}
                      className="!h-3.5 sm:!h-4"
                    />
                    <SkeletonLine
                      width="w-32 sm:w-40"
                      className="!h-2.5 !mt-1 !opacity-50"
                    />
                  </div>
                </div>
                <SkeletonLine
                  width="w-12 sm:w-16"
                  className="!h-5 sm:!h-6 !rounded-full shrink-0"
                />
              </div>
              <SkeletonLine
                width="w-3/4"
                className="!h-2.5 sm:!h-3 mt-2.5 sm:mt-3"
              />
            </div>
          ))}
        </div>
        {/* Mobile */}
        <div className="space-y-3 sm:hidden">
          {Array.from({ length: 4 }).map((_, i) => (
            <div key={i} className="glass-card rounded-xl p-4">
              <div className="flex items-center justify-between gap-2">
                <div className="flex items-center gap-2 min-w-0">
                  <div className="skeleton-line size-9 rounded-full shrink-0" />
                  <div className="min-w-0">
                    <SkeletonLine
                      width={i % 2 === 0 ? "w-16" : "w-20"}
                      className="!h-3.5"
                    />
                    <SkeletonLine
                      width="w-28"
                      className="!h-2.5 !mt-1 !opacity-50"
                    />
                  </div>
                </div>
                <SkeletonLine
                  width="w-12"
                  className="!h-5 !rounded-full shrink-0"
                />
              </div>
              <SkeletonLine width="w-3/4" className="!h-2.5 mt-2" />
            </div>
          ))}
        </div>
        {/* Pagination placeholder */}
        <PanelPaginationSkeleton variant="transparent" />
      </div>
    </div>
  );
}

/** Scheduled task panel: header + grid of task cards matching real layout */
export function ScheduledTaskPanelSkeleton() {
  return (
    <div className="glass-shell scheduled-task-panel flex h-full flex-col min-h-0 animate-fade-in">
      <PanelHeaderSkeleton hasSearch={false} />

      <div className="flex-1 overflow-y-auto px-4 py-3 sm:p-6">
        <div className="grid auto-grid-cols gap-3">
          {Array.from({ length: PANEL_CARD_SKELETON_COUNT }).map((_, i) => (
            <div
              key={i}
              className="group flex h-full flex-col overflow-hidden rounded-xl border border-[var(--theme-border)] bg-[var(--theme-bg-card)] p-4 sm:p-5 shadow-sm"
            >
              <div className="flex flex-col gap-2.5">
                {/* Title + status badge */}
                <div className="flex flex-wrap items-center gap-2">
                  <SkeletonLine
                    width={i % 2 === 0 ? "w-40 sm:w-56" : "w-32 sm:w-44"}
                    className="!h-[15px] sm:!h-[15px]"
                  />
                  <SkeletonLine
                    width="w-14 sm:w-16"
                    className="!h-5 !rounded-full shrink-0"
                  />
                </div>

                {/* Description (2-line clamped in real card) */}
                <div className="space-y-1">
                  <SkeletonLine width="w-full" className="!h-2.5 sm:!h-3" />
                  <SkeletonLine
                    width={i % 2 === 0 ? "w-4/5" : "w-2/3"}
                    className="!h-2.5 sm:!h-3"
                  />
                </div>

                {/* Meta pills */}
                <div className="my-3 flex flex-wrap gap-1.5">
                  {[0, 1, 2].map((j) => (
                    <SkeletonLine
                      key={j}
                      width={
                        j === 0
                          ? "w-24 sm:w-32"
                          : j === 1
                            ? "w-20 sm:w-28"
                            : "w-16 sm:w-24"
                      }
                      className="!h-[26px] !rounded-full"
                    />
                  ))}
                </div>

                {/* Subtle last-run info */}
                <div className="flex items-center gap-2 text-[11px] mb-2">
                  <SkeletonLine width="w-12 sm:w-14" className="!h-3" />
                  <SkeletonLine width="w-20 sm:w-28" className="!h-3" />
                  <SkeletonLine
                    width="w-12 sm:w-14"
                    className="!h-4 !rounded-full shrink-0"
                  />
                </div>
              </div>

              {/* Action buttons footer */}
              <div className="mt-auto flex items-center gap-2 border-t border-[var(--theme-border-faint)] pt-3 mt-3.5">
                <div className="ml-auto" />
                {[0, 1, 2, 3].map((j) => (
                  <div key={j} className="skeleton-line size-8 rounded-lg" />
                ))}
              </div>
            </div>
          ))}
        </div>

        {/* Pagination placeholder */}
        <PanelPaginationSkeleton variant="transparent" />
      </div>
    </div>
  );
}

/** Task session list (drill-down from scheduled task panel): header with subtitle + back button + session cards */
export function TaskSessionListSkeleton() {
  return (
    <div className="glass-shell flex h-full flex-col min-h-0 animate-fade-in">
      <PanelHeaderSkeleton hasSearch={false} hasSubtitle />
      <div className="flex-1 overflow-y-auto px-4 py-3 sm:p-6">
        <div className="scheduled-task-list">
          {Array.from({ length: 8 }).map((_, i) => (
            <div
              key={i}
              className="glass-card scheduled-task-session-card w-full text-left border border-[var(--theme-border)]"
            >
              {/* Left indicator — matches .scheduled-task-session-card__indicator (2.5rem × 2.5rem) */}
              <div className="scheduled-task-session-card__indicator">
                <div className="skeleton-line size-4 rounded" />
              </div>
              {/* Body — matches .scheduled-task-session-card__body (grid, gap: 0.25rem) */}
              <div className="scheduled-task-session-card__body">
                <SkeletonLine
                  width={i % 2 === 0 ? "w-2/3" : "w-1/2"}
                  className="!h-[14px] sm:!h-[15px]"
                />
                <div className="scheduled-task-session-card__meta">
                  <SkeletonLine
                    width="w-16 sm:w-20"
                    className="!h-2.5 !opacity-50"
                  />
                  <SkeletonLine width="w-3" className="!h-2.5 !opacity-30" />
                  <SkeletonLine
                    width="w-20 sm:w-28"
                    className="!h-2.5 !opacity-50"
                  />
                </div>
              </div>
              {/* Trail — matches .scheduled-task-session-card__trail (unread badge + chevron) */}
              <div className="scheduled-task-session-card__trail flex items-center gap-2 shrink-0">
                {i % 3 === 0 && (
                  <div className="skeleton-line size-5 rounded-full" />
                )}
                <div className="skeleton-line size-4 rounded shrink-0" />
              </div>
            </div>
          ))}
        </div>
        {/* Pagination placeholder */}
        <PanelPaginationSkeleton variant="transparent" />
      </div>
    </div>
  );
}
