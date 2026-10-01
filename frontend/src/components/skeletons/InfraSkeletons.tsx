import { SkeletonLine } from "./primitives";
import { PanelHeaderSkeleton } from "./PanelHeaderSkeleton";
import {
  PANEL_CARD_SKELETON_COUNT,
  PANEL_ROW_SKELETON_COUNT,
  PanelPaginationSkeleton,
} from "./PanelSkeletonHelpers";

/** MCP panel: card grid matching real MCPServerCard (pps-card) structure */
export function MCPPanelSkeleton() {
  return (
    <div className="glass-shell flex h-full flex-col min-h-0 animate-fade-in">
      <PanelHeaderSkeleton hasSubtitle hasSearchAccessory />
      <div className="panel-body flex-1 min-h-0 overflow-y-auto">
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
                  background: `linear-gradient(45deg, ${
                    [
                      "var(--theme-primary-light)",
                      "color-mix(in srgb, var(--theme-primary-light) 60%, var(--theme-bg))",
                      "var(--theme-bg-card)",
                    ][i % 3]
                  }, var(--theme-bg-card))`,
                }}
              >
                {/* Status badges on banner */}
                <div className="absolute inset-0 flex items-center justify-end px-2 gap-1.5">
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
              <div className="flex flex-1 flex-col p-4 pt-5">
                <div className="flex items-start gap-3">
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
                {/* Footer */}
                <div className="scb__footer flex items-center justify-between gap-2">
                  <div className="flex items-center gap-0.5">
                    <div className="skeleton-line size-7 rounded-lg" />
                    <div className="skeleton-line size-7 rounded-lg" />
                  </div>
                  <div className="skeleton-line w-10 sm:w-12 h-5 !rounded-full" />
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>
      <PanelPaginationSkeleton />
    </div>
  );
}

/** List-only variant for FeedbackPanel, whose header and summary stay mounted. */
export function FeedbackListSkeleton() {
  return (
    <div aria-hidden="true">
      {Array.from({ length: PANEL_ROW_SKELETON_COUNT }).map((_, i) => (
        <div
          key={i}
          className="panel-inset border-b border-[var(--theme-border)] py-4 last:border-b-0"
        >
          <div className="flex items-center justify-between gap-2 mb-3">
            <div className="flex items-center gap-2 min-w-0">
              <div className="skeleton-line size-7 shrink-0 rounded-full" />
              <SkeletonLine width="w-20" className="!h-3" />
            </div>
            <SkeletonLine width="w-24" className="!h-3" />
          </div>
          <div className="space-y-2">
            <SkeletonLine width="w-3/4" />
            <SkeletonLine width="w-1/2" />
          </div>
          <div className="mt-2.5 flex justify-between">
            <SkeletonLine width="w-24" className="!h-3" />
            <SkeletonLine width="w-12" className="!h-3" />
          </div>
        </div>
      ))}
    </div>
  );
}

export function FeedbackPanelSkeleton() {
  return (
    <div className="glass-shell flex h-full min-h-0 flex-col animate-fade-in">
      <PanelHeaderSkeleton
        hasSearch={false}
        hasSubtitle
        className="panel-header--section-switch"
      />
      <div className="panel-summary mb-4 rounded-2xl p-4" aria-hidden="true">
        <div className="flex items-center gap-5">
          <div className="skeleton-line size-20 shrink-0 rounded-full" />
          <div className="min-w-0 flex-1 space-y-2.5">
            <SkeletonLine />
            <SkeletonLine />
            <SkeletonLine width="w-1/2" />
          </div>
        </div>
      </div>
      <div className="panel-scroll min-h-0 flex-1 overflow-y-auto">
        <FeedbackListSkeleton />
      </div>
      <PanelPaginationSkeleton />
    </div>
  );
}

/** Scheduled task panel: header + grid of task cards matching real layout */
export function ScheduledTaskPanelSkeleton() {
  return (
    <div className="glass-shell scheduled-task-panel flex h-full flex-col min-h-0 animate-fade-in">
      <PanelHeaderSkeleton hasSearch hasSubtitle />

      <div className="panel-body flex-1 min-h-0 overflow-y-auto">
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
                <div className="flex items-center gap-2 text-11 mb-2">
                  <SkeletonLine width="w-12 sm:w-14" className="!h-3" />
                  <SkeletonLine width="w-20 sm:w-28" className="!h-3" />
                  <SkeletonLine
                    width="w-12 sm:w-14"
                    className="!h-4 !rounded-full shrink-0"
                  />
                </div>
              </div>

              {/* Action buttons footer */}
              <div className="mt-auto flex items-center gap-2 pt-3 mt-3.5">
                <div className="ml-auto" />
                {[0, 1, 2, 3].map((j) => (
                  <div key={j} className="skeleton-line size-8 rounded-lg" />
                ))}
              </div>
            </div>
          ))}
        </div>
      </div>
      <PanelPaginationSkeleton />
    </div>
  );
}

/** Task session list (drill-down from scheduled task panel): header with subtitle + back button + session cards */
export function TaskSessionListSkeleton() {
  return (
    <div className="glass-shell flex h-full flex-col min-h-0 animate-fade-in">
      <PanelHeaderSkeleton hasSearch={false} hasSubtitle />
      <div className="panel-body flex-1 min-h-0 overflow-y-auto">
        <div className="scheduled-task-list">
          {Array.from({ length: PANEL_ROW_SKELETON_COUNT }).map((_, i) => (
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
      </div>
      <PanelPaginationSkeleton />
    </div>
  );
}
