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
          {/* Banner — matches scb__banner h-12 with 45deg gradient */}
          <div
            className="h-12 w-full shrink-0 relative"
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
            {/* Banner overlay pills — matches bannerOverlay position */}
            <div className="absolute inset-0 flex items-start justify-end px-2 py-2 z-[3]">
              {i % 2 === 0 && (
                <div className="skeleton-line h-4 w-14 rounded-full opacity-80" />
              )}
            </div>
            {/* Banner leading overlay — matches bannerLeadingOverlay (skills only) */}
            {!marketplace && i % 3 === 0 && (
              <div className="absolute inset-0 flex items-start justify-start px-2 py-2 z-[3]">
                <div className="flex items-center gap-1.5">
                  <div className="skeleton-line size-5 rounded-md opacity-70" />
                  <div className="skeleton-line size-5 rounded-md opacity-70" />
                </div>
              </div>
            )}
          </div>
          {/* Content — matches SkillBaseCard inner: p-4, -mt-3 pt-5 */}
          <div className="flex flex-1 flex-col -mt-3 pt-5 p-4">
            {/* Icon ring + title + statusPills — gap-3 matches SkillBaseCard */}
            <div className="flex items-start gap-3">
              <div className="scb__icon-ring shrink-0 skeleton-line" />
              <div className="min-w-0 flex-1">
                <SkeletonLine
                  width={i % 3 === 0 ? "w-3/4" : "w-1/2"}
                  className="!h-[15px] sm:!h-[16px]"
                />
                {/* statusPills skeleton — e.g. source pill or date/author */}
                {marketplace ? (
                  <SkeletonLine
                    width="w-24 sm:w-28"
                    className="!h-2.5 sm:!h-3 mt-1.5 !opacity-60"
                  />
                ) : (
                  <SkeletonLine
                    width="w-14 sm:w-16"
                    className="!h-4 !rounded-full mt-1.5"
                  />
                )}
              </div>
            </div>

            {/* Description — matches mt-3 text-13 line-clamp-2 */}
            <div className="mt-3 space-y-1.5">
              <SkeletonLine width="w-full" className="!h-2.5 sm:!h-3" />
              <SkeletonLine
                width={i % 2 === 0 ? "w-5/6" : "w-2/3"}
                className="!h-2.5 sm:!h-3"
              />
            </div>

            {/* Tags — matches SkillBaseCard tags section */}
            {marketplace ? (
              <div className="mt-3 flex flex-wrap items-center gap-1.5">
                <SkeletonLine
                  width="w-12 sm:w-14"
                  className="!h-[22px] !rounded-full"
                />
                <SkeletonLine
                  width="w-10 sm:w-12"
                  className="!h-[22px] !rounded-full"
                />
                <SkeletonLine
                  width="w-8 sm:w-10"
                  className="!h-[22px] !rounded-full"
                />
              </div>
            ) : (
              <div className="mt-3 flex flex-wrap gap-2">
                <SkeletonLine
                  width="w-14 sm:w-16"
                  className="!h-[22px] !rounded-full"
                />
                <SkeletonLine
                  width="w-20 sm:w-24"
                  className="!h-[22px] !rounded-full"
                />
                <SkeletonLine
                  width="w-12 sm:w-14"
                  className="!h-[22px] !rounded-full"
                />
              </div>
            )}

            <div className="flex-1" />

            {/* Meta section — matches SkillBaseCard meta area */}
            {marketplace ? (
              <div className="mt-4 flex items-center justify-between gap-2">
                <div className="flex items-center gap-2">
                  <SkeletonLine
                    width="w-8 sm:w-10"
                    className="!h-3.5 !rounded-full"
                  />
                  <div className="size-1 rounded-full bg-[var(--theme-border)]" />
                  <SkeletonLine width="w-6" className="!h-3.5 !rounded-full" />
                </div>
                <div className="flex items-center gap-1.5">
                  <div className="skeleton-line size-7 rounded-lg" />
                  <div className="skeleton-line size-7 rounded-lg" />
                  {i % 2 === 0 && (
                    <div className="skeleton-line size-7 rounded-lg" />
                  )}
                </div>
              </div>
            ) : (
              <>
                {/* Meta pills — matches skill-meta-pill area */}
                <div className="mt-4 flex flex-wrap items-center gap-2">
                  <SkeletonLine
                    width="w-16 sm:w-20"
                    className="!h-[26px] !rounded-full"
                  />
                  <SkeletonLine
                    width="w-24 sm:w-28"
                    className="!h-[26px] !rounded-full"
                  />
                </div>
                {/* Footer — matches scb__footer with action buttons */}
                <div className="scb__footer">
                  <div className="flex items-center gap-1">
                    <div className="skeleton-line size-7 rounded-[7px]" />
                    <div className="skeleton-line size-6 rounded-[6px]" />
                    {i % 2 === 0 && (
                      <div className="skeleton-line size-6 rounded-[6px]" />
                    )}
                    <div className="ml-auto" />
                    <div className="skeleton-line size-7 rounded-[7px]" />
                  </div>
                </div>
              </>
            )}
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
    <div className="skill-theme-shell flex h-full flex-col min-h-0 animate-fade-in">
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
    <div className="skill-theme-shell flex h-full flex-col min-h-0 animate-fade-in">
      <PanelHeaderSkeleton />
      <div className="skill-content-area flex-1 overflow-y-auto py-2 sm:py-4 px-4 sm:p-6 lg:px-8 lg:py-8">
        <SkillCardsSkeleton marketplace />
        {/* Pagination placeholder */}
        <PanelPaginationSkeleton />
      </div>
    </div>
  );
}
