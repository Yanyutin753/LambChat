import { SkeletonLine } from "./primitives";
import { PanelHeaderSkeleton } from "./PanelHeaderSkeleton";
import {
  PANEL_CARD_SKELETON_COUNT,
  PanelPaginationSkeleton,
} from "./PanelSkeletonHelpers";

export function MemoryPanelSkeleton() {
  return (
    <div className="glass-shell flex h-full flex-col min-h-0">
      <PanelHeaderSkeleton hasSearch hasSubtitle hasSearchAccessory />
      <div className="panel-body flex-1 min-h-0 overflow-y-auto">
        <div className="grid gap-3 auto-grid-cols">
          {Array.from({ length: PANEL_CARD_SKELETON_COUNT }).map((_, i) => (
            <div
              key={i}
              className="scb flex h-full flex-col overflow-hidden bg-[var(--theme-bg-card)]"
            >
              <div className="scb__banner skeleton-line h-12 shrink-0" />
              <div className="scb__body flex flex-1 flex-col p-3">
                <div className="scb__header flex items-center gap-2">
                  <div className="scb__icon-ring skeleton-line shrink-0" />
                  <div className="min-w-0 flex-1">
                    <SkeletonLine
                      width={i % 2 === 0 ? "w-3/4" : "w-2/3"}
                      className="!h-4"
                    />
                    <div className="mt-1 flex gap-1.5">
                      <SkeletonLine width="w-12" className="!h-4 !rounded-full" />
                      <SkeletonLine width="w-16" className="!h-4 !rounded-full" />
                    </div>
                  </div>
                </div>
                <div className="mt-2 space-y-2">
                  <SkeletonLine width="w-full" className="!h-3" />
                  <SkeletonLine
                    width={i % 3 === 0 ? "w-4/5" : "w-2/3"}
                    className="!h-3"
                  />
                </div>
                <div className="mt-2 flex flex-wrap gap-1.5">
                  <SkeletonLine width="w-12" className="!h-5 !rounded-md" />
                  <SkeletonLine width="w-16" className="!h-5 !rounded-md" />
                  <SkeletonLine width="w-10" className="!h-5 !rounded-md" />
                </div>

                <div className="scb__footer flex items-center justify-between gap-2">
                  <div className="min-w-0 flex flex-1 flex-wrap items-center gap-2">
                    <SkeletonLine width="w-32" className="!h-3" />
                    <SkeletonLine width="w-16" className="!h-3" />
                  </div>
                  <div className="skeleton-line size-9 shrink-0 rounded-lg" />
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
