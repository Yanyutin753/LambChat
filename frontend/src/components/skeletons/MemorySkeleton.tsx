import { SkeletonLine } from "./primitives";
import { PanelHeaderSkeleton } from "./PanelHeaderSkeleton";
import {
  PANEL_CARD_SKELETON_COUNT,
  PanelPaginationSkeleton,
} from "./PanelSkeletonHelpers";

export function MemoryPanelSkeleton() {
  return (
    <div className="glass-shell flex h-full flex-col min-h-0 animate-fade-in">
      <PanelHeaderSkeleton hasSearch hasSubtitle hasSearchAccessory />
      <div className="panel-body flex-1 min-h-0 overflow-y-auto">
        <div className="grid gap-3 auto-grid-cols">
          {Array.from({ length: PANEL_CARD_SKELETON_COUNT }).map((_, i) => (
            <div
              key={i}
              className="glass-card group relative flex flex-col rounded-xl p-4 sm:p-5"
            >
              <div className="absolute right-3 top-3">
                <div className="skeleton-line size-5 rounded-md opacity-70" />
              </div>

              <div className="min-w-0 flex-1">
                <div className="mb-2 flex flex-wrap items-center gap-2 pr-8">
                  <SkeletonLine
                    width={i % 2 === 0 ? "w-16" : "w-20"}
                    className="!h-5 !rounded-full"
                  />
                  <SkeletonLine width="w-14" className="!h-4 !rounded-full" />
                  <SkeletonLine width="w-20" className="!h-3 !opacity-50" />
                </div>

                <SkeletonLine
                  width={i % 2 === 0 ? "w-3/4" : "w-2/3"}
                  className="!h-4 sm:!h-5"
                />

                <div className="mt-2 space-y-1.5">
                  <SkeletonLine width="w-full" className="!h-3" />
                  <SkeletonLine
                    width={i % 3 === 0 ? "w-4/5" : "w-2/3"}
                    className="!h-3"
                  />
                </div>
              </div>

              <div className="my-3 flex flex-wrap gap-1.5">
                <SkeletonLine width="w-12" className="!h-5 !rounded-md" />
                <SkeletonLine width="w-16" className="!h-5 !rounded-md" />
                <SkeletonLine width="w-10" className="!h-5 !rounded-md" />
              </div>

              <div className="mt-auto flex items-center gap-2 pt-3">
                <SkeletonLine width="w-20" className="!h-5 !rounded-full" />
                <div className="ml-auto" />
                <div className="skeleton-line size-8 rounded-lg" />
                <div className="skeleton-line size-8 rounded-lg" />
              </div>
            </div>
          ))}
        </div>
      </div>
      <PanelPaginationSkeleton />
    </div>
  );
}
