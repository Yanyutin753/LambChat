import { SkeletonLine } from "./primitives";
import { PanelHeaderSkeleton } from "./PanelHeaderSkeleton";
import {
  PANEL_CARD_SKELETON_COUNT,
  PanelPaginationSkeleton,
} from "./PanelSkeletonHelpers";

/** Users panel: table rows (desktop) + cards (mobile) */
export function UsersPanelSkeleton() {
  return (
    <div className="glass-shell flex h-full flex-col min-h-0 animate-fade-in">
      <PanelHeaderSkeleton />
      <div className="flex-1 overflow-y-auto min-h-0 py-2 sm:py-4 px-4">
        {/* Desktop table */}
        <div className="hidden sm:block">
          <div className="glass-card rounded-xl !p-0 overflow-hidden">
            {/* Table header */}
            <div
              className="flex items-center gap-4 px-6 py-3"
              style={{
                backgroundColor:
                  "var(--glass-bg-subtle, color-mix(in srgb, var(--theme-bg) 80%, white))",
              }}
            >
              <SkeletonLine width="w-24 xl:w-28" className="!h-3 !rounded" />
              <SkeletonLine
                width="w-32 xl:w-44"
                className="!h-3 !rounded flex-1"
              />
              <SkeletonLine width="w-20 xl:w-24" className="!h-3 !rounded" />
              <SkeletonLine width="w-16" className="!h-3 !rounded" />
              <SkeletonLine width="w-20 xl:w-28" className="!h-3 !rounded" />
              <SkeletonLine width="w-16 xl:w-20" className="!h-3 !rounded" />
            </div>
            {Array.from({ length: 8 }).map((_, i) => (
              <div
                key={i}
                className="flex items-center gap-4 px-6 py-4"
                style={{
                  borderTop:
                    "1px solid var(--glass-border, var(--theme-border))",
                }}
              >
                <div className="flex items-center gap-3 w-28 xl:w-32 shrink-0">
                  <div className="skeleton-line size-8 rounded-full shrink-0" />
                  <SkeletonLine
                    width={i % 2 === 0 ? "w-16 xl:w-20" : "w-20 xl:w-24"}
                    className="!h-4"
                  />
                </div>
                <SkeletonLine
                  width={i % 3 === 0 ? "w-36 xl:w-52" : "w-44 xl:w-60"}
                  className="!h-3.5 flex-1"
                />
                <div className="flex gap-1 w-20 xl:w-24 shrink-0">
                  <SkeletonLine width="w-14" className="!h-5 !rounded-full" />
                </div>
                <SkeletonLine
                  width="w-16"
                  className="!h-5 !rounded-full shrink-0"
                />
                <SkeletonLine width="w-20" className="!h-3 shrink-0" />
                <div className="flex gap-1 w-16 shrink-0">
                  <div className="skeleton-line size-7 rounded-lg" />
                  <div className="skeleton-line size-7 rounded-lg" />
                </div>
              </div>
            ))}
          </div>
        </div>
        {/* Mobile cards */}
        <div className="space-y-3 sm:hidden">
          {Array.from({ length: 4 }).map((_, i) => (
            <div key={i} className="glass-card rounded-xl p-4">
              <div className="flex items-start gap-3">
                <div className="skeleton-line size-10 rounded-full shrink-0" />
                <div className="flex-1 min-w-0">
                  <SkeletonLine
                    width={i % 2 === 0 ? "w-24" : "w-20"}
                    className="!h-4"
                  />
                  <SkeletonLine width="w-36" className="!h-3 mt-1" />
                </div>
                <div className="skeleton-line size-7 rounded-lg shrink-0" />
              </div>
              <div className="mt-3 flex flex-wrap gap-1.5">
                <SkeletonLine width="w-14" className="!h-5 !rounded-full" />
                <SkeletonLine width="w-16" className="!h-5 !rounded-full" />
              </div>
              <div className="mt-3 flex items-center justify-between">
                <SkeletonLine width="w-16" className="!h-5 !rounded-full" />
                <SkeletonLine width="w-20" className="!h-3" />
              </div>
            </div>
          ))}
        </div>
        {/* Pagination placeholder */}
        <PanelPaginationSkeleton variant="wide" />
      </div>
    </div>
  );
}

/** Roles panel: card grid matching real RolesPanel layout (glass-card + auto-grid-cols) */
export function RolesPanelSkeleton() {
  return (
    <div className="glass-shell flex h-full flex-col min-h-0 animate-fade-in">
      <PanelHeaderSkeleton />
      <div className="flex-1 overflow-y-auto py-2 sm:py-4 px-4">
        <div className="grid gap-3 auto-grid-cols">
          {Array.from({ length: PANEL_CARD_SKELETON_COUNT }).map((_, i) => (
            <div
              key={i}
              className="glass-card relative flex flex-col rounded-xl p-4 sm:p-5"
            >
              {/* Header badges — matches real ShieldCheck pill + permission count */}
              <div className="flex flex-wrap items-center gap-2 mb-2">
                <SkeletonLine
                  width="w-14 sm:w-16"
                  className="!h-[11px] !rounded-full"
                />
                <SkeletonLine width="w-16" className="!h-[11px] !opacity-50" />
              </div>

              {/* Title */}
              <SkeletonLine
                width={i % 2 === 0 ? "w-24 sm:w-32" : "w-28 sm:w-36"}
                className="!h-4"
              />

              {/* Description — 2-line clamp */}
              <div className="mt-1 space-y-1">
                <SkeletonLine width="w-full" className="!h-2.5 sm:!h-3" />
                <SkeletonLine
                  width={i % 2 === 0 ? "w-5/6" : "w-3/4"}
                  className="!h-2.5 sm:!h-3"
                />
              </div>

              {/* Permission tags — matches real flex-wrap gap-1.5 chips */}
              <div className="mt-3 mb-2 flex flex-wrap gap-1.5">
                {[0, 1, 2].map((j) => (
                  <SkeletonLine
                    key={j}
                    width={j === 0 ? "w-14" : j === 1 ? "w-20" : "w-12"}
                    className="!h-[11px] !rounded-md"
                  />
                ))}
              </div>

              {/* Footer actions — matches real border-t with edit/delete buttons */}
              <div className="mt-auto flex items-center gap-2 border-t border-[var(--glass-border)] pt-3 mt-3.5">
                <div className="ml-auto" />
                <div className="skeleton-line size-8 rounded-lg" />
                <div className="skeleton-line size-8 rounded-lg" />
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
