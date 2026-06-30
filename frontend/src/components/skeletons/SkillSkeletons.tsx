import { SkeletonLine } from "./primitives";
import { PanelHeaderSkeleton } from "./PanelHeaderSkeleton";
import {
  PANEL_CARD_SKELETON_COUNT,
  PanelPaginationSkeleton,
} from "./PanelSkeletonHelpers";

function SkillCardsSkeleton({
  count = PANEL_CARD_SKELETON_COUNT,
  marketplace = false,
}: {
  count?: number;
  marketplace?: boolean;
}) {
  return (
    <div
      className={
        marketplace
          ? "grid auto-grid-cols gap-5"
          : "skill-grid grid auto-grid-cols gap-4"
      }
    >
      {Array.from({ length: count }).map((_, i) => (
        <div key={i} className="scb">
          <div
            className="h-12 w-full shrink-0 relative"
            style={{
              background: `linear-gradient(135deg, ${
                [
                  "var(--theme-primary-light)",
                  "color-mix(in srgb, var(--theme-primary-light) 60%, var(--theme-bg))",
                  "var(--theme-bg-card)",
                ][i % 3]
              }, var(--theme-bg-card))`,
            }}
          />
          <div className="flex flex-1 flex-col -mt-3 pt-5 p-3 sm:p-4">
            <div className="flex items-start gap-2.5 sm:gap-3">
              <div className="scb__icon-ring shrink-0 skeleton-line" />
              <div className="min-w-0 flex-1">
                <SkeletonLine
                  width={i % 3 === 0 ? "w-3/4" : "w-1/2"}
                  className="!h-[15px] sm:!h-[16px]"
                />
                {marketplace && (
                  <SkeletonLine
                    width="w-16 sm:w-20"
                    className="!h-2.5 sm:!h-3 mt-1"
                  />
                )}
              </div>
            </div>
            {!marketplace && (
              <div className="mt-1.5 sm:mt-2">
                <SkeletonLine
                  width="w-14 sm:w-16"
                  className="!h-4 !rounded-full"
                />
              </div>
            )}
            <div className="mt-2 sm:mt-3 space-y-1.5">
              <SkeletonLine width="w-full" className="!h-2.5 sm:!h-3" />
              <SkeletonLine
                width={i % 2 === 0 ? "w-5/6" : "w-2/3"}
                className="!h-2.5 sm:!h-3"
              />
            </div>
            {marketplace ? (
              <div className="mt-2.5 sm:mt-3 flex items-center justify-between">
                <SkeletonLine
                  width="w-12 sm:w-14"
                  className="!h-4 sm:!h-5 !rounded-full"
                />
                <div className="flex items-center gap-1.5">
                  <div className="skeleton-line size-7 rounded-lg" />
                  <div className="skeleton-line size-7 rounded-lg" />
                </div>
              </div>
            ) : (
              <div className="mt-3 flex flex-wrap gap-1.5 sm:gap-2">
                <SkeletonLine
                  width="w-14 sm:w-16"
                  className="!h-4 sm:!h-5 !rounded-full"
                />
                <SkeletonLine
                  width="w-20 sm:w-24"
                  className="!h-4 sm:!h-5 !rounded-full"
                />
                <SkeletonLine
                  width="w-12 sm:w-14"
                  className="!h-4 sm:!h-5 !rounded-full"
                />
              </div>
            )}
            <div className="flex-1" />
          </div>
        </div>
      ))}
    </div>
  );
}

export function SkillsListSkeleton() {
  return (
    <div className="flex h-full min-h-0 flex-col animate-fade-in">
      <PanelHeaderSkeleton hasSubtitle={false} />
      <div className="skill-content-area flex-1 overflow-y-auto py-2 sm:py-4 px-4 lg:px-8 lg:py-8">
        <SkillCardsSkeleton />
        <PanelPaginationSkeleton />
      </div>
    </div>
  );
}

/** Skills panel: card grid matching SkillBaseCard (.scb) structure */
export function SkillsPanelSkeleton() {
  return (
    <div className="glass-shell flex h-full flex-col min-h-0 animate-fade-in">
      <PanelHeaderSkeleton />
      <div className="skill-content-area flex-1 overflow-y-auto py-2 sm:py-4 px-4 lg:px-8 lg:py-8">
        <SkillCardsSkeleton />
        {/* Pagination placeholder */}
        <PanelPaginationSkeleton />
      </div>
    </div>
  );
}

/** Marketplace panel: card grid matching SkillBaseCard (.scb) structure */
export function MarketplacePanelSkeleton() {
  return (
    <div className="glass-shell flex h-full flex-col min-h-0 animate-fade-in">
      <PanelHeaderSkeleton />
      <div className="skill-content-area flex-1 overflow-y-auto py-2 sm:py-4 px-4 sm:p-6 lg:px-8 lg:py-8">
        <SkillCardsSkeleton marketplace />
        {/* Pagination placeholder */}
        <PanelPaginationSkeleton />
      </div>
    </div>
  );
}
