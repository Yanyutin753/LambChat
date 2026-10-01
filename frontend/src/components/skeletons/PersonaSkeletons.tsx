import { SkeletonLine } from "./primitives";
import { PanelHeaderSkeleton } from "./PanelHeaderSkeleton";
import {
  PANEL_CARD_SKELETON_COUNT,
  PanelPaginationSkeleton,
} from "./PanelSkeletonHelpers";

export function PersonaPlazaSkeleton() {
  return (
    <div className="glass-shell flex h-full min-w-0 flex-1 flex-col min-h-0 animate-fade-in">
      <PanelHeaderSkeleton
        hasSearch
        hasSubtitle
        hasSearchAccessory
        hasSearchActions
      />
      <div className="panel-body flex-1 min-h-0 overflow-y-auto skill-content-area">
        <div className="grid auto-grid-cols gap-4 sm:gap-5">
          {Array.from({ length: PANEL_CARD_SKELETON_COUNT }).map((_, i) => (
            <div
              key={i}
              className="pps-card scb flex h-full flex-col overflow-hidden rounded-2xl border border-[var(--theme-border)] bg-[var(--theme-bg-card)]"
            >
              {/* Banner */}
              <div
                className="scb__banner h-12 w-full shrink-0 relative"
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
                {/* Banner overlay — status pill + pin/favorite buttons */}
                <div className="absolute top-2 right-2">
                  <SkeletonLine width="w-10" className="!h-3.5 !rounded-full" />
                </div>
                <div className="absolute top-2 left-2 flex gap-1.5">
                  <div className="skeleton-line size-5 rounded" />
                  <div className="skeleton-line size-5 rounded" />
                </div>
              </div>
              {/* Card body */}
              <div className="flex flex-1 flex-col p-4 pt-5">
                <div className="flex items-start gap-3">
                  <div className="scb__icon-ring shrink-0 skeleton-line" />
                  <div className="min-w-0 flex-1">
                    {/* Title — entity name (PersonaPresetCard: font-semibold font-serif) */}
                    <SkeletonLine
                      width={i % 2 === 0 ? "w-3/4" : "w-1/2"}
                      className="!h-4 font-serif"
                    />
                    {/* Metadata line — scope, status, usage count */}
                    <SkeletonLine
                      width="w-3/5"
                      className="!h-2.5 mt-1 !opacity-50"
                    />
                  </div>
                </div>
                <div className="mt-3 min-h-[3.25em] space-y-1.5">
                  <SkeletonLine width="w-full" className="!h-3" />
                  <SkeletonLine
                    width={i % 2 === 0 ? "w-5/6" : "w-2/3"}
                    className="!h-3"
                  />
                </div>
                {/* Tags */}
                <div className="mt-3 flex flex-wrap gap-1.5">
                  <SkeletonLine width="w-14" className="!h-5 !rounded-full" />
                  <SkeletonLine width="w-10" className="!h-5 !rounded-full" />
                  <SkeletonLine width="w-16" className="!h-5 !rounded-full" />
                </div>
                {/* Footer — skill count on left, action buttons on right */}
                <div
                  className="scb__footer flex items-center justify-between gap-2"
                  style={{ borderColor: "var(--theme-border)" }}
                >
                  <SkeletonLine width="w-12" className="!h-3 !opacity-50" />
                  <div className="flex gap-1.5">
                    <SkeletonLine width="w-7" className="!h-7 !rounded-lg" />
                    <SkeletonLine width="w-7" className="!h-7 !rounded-lg" />
                    <SkeletonLine width="w-7" className="!h-7 !rounded-lg" />
                    <SkeletonLine width="w-7" className="!h-7 !rounded-lg" />
                  </div>
                </div>
                <div className="flex-1" />
              </div>
            </div>
          ))}
        </div>
      </div>
      <PanelPaginationSkeleton />
    </div>
  );
}

export function PersonaPageSkeleton() {
  return (
    <div className="flex h-full w-full min-w-0 animate-fade-in">
      <PersonaPlazaSkeleton />
    </div>
  );
}
