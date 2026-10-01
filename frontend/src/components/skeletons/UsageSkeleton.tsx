import { SkeletonLine } from "./primitives";
import { PanelHeaderSkeleton } from "./PanelHeaderSkeleton";
import {
  PANEL_ROW_SKELETON_COUNT,
  PanelPaginationSkeleton,
} from "./PanelSkeletonHelpers";

/** Shared skeleton for a single insight item inside InsightStrip (border-r border-b grid item) */
function InsightItemSkeleton() {
  return (
    <div className="min-w-0 border-r border-b border-[var(--usage-border)] px-3.5 py-3 sm:px-4 sm:py-4 xl:border-b-0">
      <div className="mb-1 flex items-center gap-1.5 sm:gap-2">
        <div className="skeleton-line size-[12px] rounded shrink-0" />
        <SkeletonLine width="w-8 sm:w-10" className="!h-[11px] !opacity-60" />
      </div>
      <div className="flex items-center gap-1.5">
        <div
          className="inline-block size-[6px] shrink-0 rounded-full"
          style={{ backgroundColor: "var(--theme-primary)" }}
        />
        <SkeletonLine width="w-14 sm:w-16" className="!h-[15px] sm:!h-4" />
      </div>
      <SkeletonLine
        width="w-20 sm:w-24"
        className="!h-[10px] mt-1 !opacity-50"
      />
    </div>
  );
}

/** Shared skeleton for a ranking card with title, items, and progress bars */
function RankingCardSkeleton({ itemCount = 3 }: { itemCount?: number }) {
  return (
    <div
      className="usage-surface rounded-xl border p-3 sm:p-4"
      style={{ borderColor: "var(--usage-border)" }}
    >
      {/* Header */}
      <div className="mb-3 flex items-center gap-2">
        <div className="skeleton-line size-[14px] rounded shrink-0" />
        <SkeletonLine width="w-16 sm:w-20" className="!h-[13px] sm:!h-[14px]" />
        <div className="flex-1" />
        <SkeletonLine width="w-8" className="!h-[10px] !opacity-50" />
      </div>

      {/* Items */}
      <div className="flex flex-col gap-2.5 sm:gap-3">
        {Array.from({ length: itemCount }).map((_, i) => (
          <div key={i} className="min-w-0">
            <div className="mb-1 flex items-center gap-1.5 sm:gap-2">
              {i < 3 && (
                <div className="skeleton-line h-5 w-5 shrink-0 rounded-md" />
              )}
              <SkeletonLine
                width={i % 2 === 0 ? "w-20 sm:w-24" : "w-14 sm:w-18"}
                className="!h-[11px] sm:!h-[12px] flex-1"
              />
              <SkeletonLine
                width={i % 2 === 0 ? "w-10 sm:w-12" : "w-8 sm:w-10"}
                className="!h-[11px] sm:!h-[12px] shrink-0"
              />
            </div>
            <div className="skeleton-line h-1 w-full rounded-full !opacity-30" />
            <div className="mt-1 flex justify-between">
              <SkeletonLine width="w-8" className="!h-[10px] !opacity-40" />
              <SkeletonLine width="w-10" className="!h-[10px] !opacity-40" />
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

/** Skeleton for the MiniTrend chart card */
function MiniTrendSkeleton() {
  return (
    <div className="usage-surface usage-chart-card rounded-xl overflow-hidden">
      {/* Header */}
      <div
        className="flex items-start justify-between gap-3 border-b px-4 pt-4 pb-3 sm:px-5"
        style={{ borderColor: "var(--usage-border)" }}
      >
        <div className="flex items-center gap-2.5">
          <div
            className="skeleton-line h-8 w-8 shrink-0 rounded-lg sm:h-9 sm:w-9"
            style={{
              backgroundColor: "var(--usage-icon-bg, var(--glass-bg-subtle))",
            }}
          />
          <div className="min-w-0">
            <SkeletonLine
              width="w-20 sm:w-24"
              className="!h-[13px] sm:!h-[14px]"
            />
            <SkeletonLine
              width="w-28 sm:w-32"
              className="!h-[10px] sm:!h-[11px] mt-0.5 !opacity-50"
            />
          </div>
        </div>
        {/* Desktop pills */}
        <div className="hidden gap-1.5 sm:flex">
          <SkeletonLine width="w-12" className="!h-[10px] !rounded-full" />
          <SkeletonLine width="w-12" className="!h-[10px] !rounded-full" />
          <SkeletonLine width="w-10" className="!h-[10px] !rounded-full" />
        </div>
      </div>

      {/* Chart area */}
      <div className="px-1 py-1 sm:px-2">
        <div
          className="skeleton-line h-[180px] w-full rounded-lg sm:h-[220px]"
          style={{
            backgroundColor: "var(--usage-inset-bg, var(--glass-bg-subtle))",
          }}
        />
      </div>

      {/* Summary — Mobile (3 cols) */}
      <div
        className="grid grid-cols-3 gap-1.5 border-t px-3 py-2.5 sm:hidden"
        style={{ borderColor: "var(--usage-border)" }}
      >
        {[0, 1, 2].map((i) => (
          <div key={i}>
            <SkeletonLine width="w-8" className="!h-[9px]" />
            <SkeletonLine width="w-10" className="!h-[13px] mt-0.5" />
          </div>
        ))}
      </div>

      {/* Summary — Desktop (4 cols) */}
      <div
        className="hidden grid-cols-4 gap-2 border-t px-4 py-3 sm:grid"
        style={{ borderColor: "var(--usage-border)" }}
      >
        {[0, 1, 2, 3].map((i) => (
          <div key={i}>
            <div className="flex items-center gap-1.5">
              <div className="skeleton-line size-[10px] rounded shrink-0" />
              <SkeletonLine width="w-10" className="!h-[10px]" />
            </div>
            <SkeletonLine width="w-12" className="!h-[13px] mt-0.5" />
          </div>
        ))}
      </div>
    </div>
  );
}

/** Usage panel skeleton matching real UsagePanel layout */
export function UsagePanelSkeleton() {
  return (
    <div className="glass-shell usage-panel flex h-full min-h-0 flex-col overflow-y-auto animate-fade-in">
      {/* 1. PanelHeader with search, subtitle */}
      <PanelHeaderSkeleton hasSearch hasSubtitle hasSearchAccessory hasSearchActions hasActions={false} />

      {/* 2. KPI grid — 6 StatMetric cards in single usage-surface: grid-cols-2 sm:grid-cols-3 xl:grid-cols-6 */}
      <div className="mx-auto w-full px-4 pt-5 pb-4 sm:px-6 sm:pt-6 sm:pb-5 lg:px-8">
        <div className="usage-surface grid grid-cols-2 overflow-hidden rounded-xl md:grid-cols-4 xl:grid-cols-7">
          {Array.from({ length: 7 }).map((_, i) => (
            <div
              key={i}
              className="group relative flex min-w-0 flex-col gap-2 border-r border-b border-[var(--usage-border)] px-3.5 py-3 sm:gap-2.5 sm:px-4 sm:py-4 xl:border-b-0"
            >
              {/* Icon + label row */}
              <div className="flex items-center gap-2 sm:gap-2.5">
                <div
                  className="flex h-7 w-7 shrink-0 items-center justify-center rounded-md sm:h-8 sm:w-8"
                  style={{
                    backgroundColor:
                      "var(--usage-icon-bg, var(--glass-bg-subtle))",
                  }}
                >
                  <div className="skeleton-line size-[13px] rounded-sm" />
                </div>
                <SkeletonLine
                  width={i % 2 === 0 ? "w-10 sm:w-14" : "w-8 sm:w-12"}
                  className="!h-[10px] sm:!h-[11px]"
                />
              </div>
              {/* Value row */}
              <SkeletonLine
                width={i % 2 === 0 ? "w-14 sm:w-16" : "w-10 sm:w-12"}
                className="!h-[20px] sm:!h-[24px] pl-[2.25rem] sm:pl-[2.5rem]"
              />
              {/* Hint row */}
              <SkeletonLine
                width={i % 3 === 0 ? "w-20 sm:w-24" : "w-16 sm:w-20"}
                className="!h-[10px] sm:!h-[11px] pl-[2.25rem] sm:pl-[2.5rem] !opacity-50"
              />
            </div>
          ))}
        </div>
      </div>

      {/* 3–9. Dashboard content area */}
      <div className="mx-auto w-full flex-1 px-4 pt-0 pb-4 sm:px-6 sm:pb-6 lg:px-8">
        {/* 3. Section header: "运营总览" with LayoutDashboard icon */}
        <div className="mb-3 flex items-center gap-2.5 sm:mb-4">
          <div className="skeleton-line size-[14px] rounded shrink-0" />
          <div className="min-w-0">
            <SkeletonLine
              width="w-14 sm:w-16"
              className="!h-[13px] sm:!h-[14px]"
            />
            <SkeletonLine
              width="w-32 sm:w-40"
              className="!h-[10px] sm:!h-[11px] mt-0.5 !opacity-50"
            />
          </div>
        </div>

        {/* 4. InsightStrip: 6 insight items in single surface — grid-cols-2 sm:grid-cols-3 xl:grid-cols-6 */}
        <div className="usage-insight-strip usage-surface mb-4 grid grid-cols-2 overflow-hidden rounded-xl sm:grid-cols-3 xl:grid-cols-6">
          {Array.from({ length: 6 }).map((_, i) => (
            <InsightItemSkeleton key={i} />
          ))}
        </div>

        {/* 5. Chart + Rankings: two-column grid (xl:grid-cols-[1.5fr_1fr]) */}
        <div className="mb-5 grid gap-5 sm:mb-6 xl:grid-cols-[minmax(0,1.45fr)_minmax(24rem,0.95fr)]">
          {/* Left: MiniTrend chart card */}
          <MiniTrendSkeleton />
          {/* Right: 2 stacked RankingList cards */}
          <div className="grid gap-5 xl:grid-cols-1">
            <RankingCardSkeleton itemCount={3} />
            <RankingCardSkeleton itemCount={3} />
          </div>
        </div>

        {/* 6. Bottom ranking grid (grid-cols-1 sm:grid-cols-2 2xl:grid-cols-4): 4 cards */}
        <div className="mb-5 grid grid-cols-1 gap-5 sm:mb-6 sm:grid-cols-2 xl:grid-cols-2 2xl:grid-cols-4">
          <RankingCardSkeleton itemCount={3} />
          <RankingCardSkeleton itemCount={3} />
          <RankingCardSkeleton itemCount={3} />
          <RankingCardSkeleton itemCount={3} />
        </div>

        {/* 7. Optional triggers DistributionList */}
        <div className="mb-4 sm:mb-5">
          <RankingCardSkeleton itemCount={3} />
        </div>

        {/* 8. UsageLogsTable with SectionHeader + Desktop / Tablet / Mobile skeletons */}
        <>
          {/* SectionHeader skeleton */}
          <div className="usage-section-header mb-3 flex items-center justify-between gap-4 sm:mb-4">
            <div className="flex items-center gap-2">
              <div className="skeleton-line size-[14px] rounded shrink-0" />
              <SkeletonLine width="w-14 sm:w-16" className="!h-[14px]" />
            </div>
            <SkeletonLine width="w-16" className="!h-[11px] !opacity-50" />
          </div>

          {/* Desktop table skeleton (lg+) — matches DesktopTable structure */}
          <div className="hidden lg:block">
            <div className="usage-surface overflow-x-auto rounded-xl">
              {/* Table header */}
              <div
                className="flex items-center gap-4 px-4 py-2.5"
                style={{
                  borderBottom: "1px solid var(--usage-border)",
                  backgroundColor:
                    "var(--usage-inset-bg, var(--glass-bg-subtle))",
                }}
              >
                <SkeletonLine
                  width="w-14 xl:w-16"
                  className="!h-[11px] !rounded"
                />
                <SkeletonLine
                  width="w-14 xl:w-16"
                  className="!h-[11px] !rounded"
                />
                <SkeletonLine
                  width="w-14 xl:w-16"
                  className="!h-[11px] !rounded"
                />
                <SkeletonLine
                  width="w-16 xl:w-18"
                  className="!h-[11px] !rounded"
                />
                <div className="flex-1" />
                <SkeletonLine
                  width="w-12"
                  className="!h-[11px] !rounded text-right"
                />
                <SkeletonLine
                  width="w-12"
                  className="!h-[11px] !rounded text-right"
                />
                <SkeletonLine
                  width="w-12"
                  className="!h-[11px] !rounded text-right"
                />
                <SkeletonLine
                  width="w-12"
                  className="!h-[11px] !rounded text-right"
                />
                <SkeletonLine
                  width="w-12"
                  className="!h-[11px] !rounded text-right"
                />
                <SkeletonLine
                  width="w-12"
                  className="!h-[11px] !rounded text-center"
                />
              </div>
              {/* Table rows */}
              {Array.from({ length: PANEL_ROW_SKELETON_COUNT }).map((_, i) => (
                <div
                  key={i}
                  className="flex items-center gap-4 px-4 py-2.5"
                  style={{ borderBottom: "1px solid var(--usage-border)" }}
                >
                  <SkeletonLine width="w-20" className="!h-[13px] shrink-0" />
                  {/* Admin avatar + username */}
                  <div className="flex items-center gap-2 shrink-0">
                    <div
                      className="skeleton-line h-7 w-7 rounded-full shrink-0"
                      style={{
                        backgroundColor:
                          "var(--usage-icon-bg, var(--glass-bg-subtle))",
                      }}
                    />
                    <SkeletonLine width="w-10" className="!h-[13px] shrink-0" />
                  </div>
                  {/* Model code badge */}
                  <SkeletonLine
                    width="w-20 sm:w-24"
                    className="!h-[12px] shrink-0 !rounded-md"
                  />
                  {/* Agent name */}
                  <SkeletonLine
                    width="w-16 sm:w-20"
                    className="!h-[13px] shrink-0"
                  />
                  <div className="flex-1" />
                  <SkeletonLine
                    width="w-10"
                    className="!h-[13px] shrink-0 text-right"
                  />
                  <SkeletonLine
                    width="w-10"
                    className="!h-[13px] shrink-0 text-right"
                  />
                  <SkeletonLine
                    width="w-10"
                    className="!h-[13px] shrink-0 text-right"
                  />
                  <SkeletonLine
                    width="w-10"
                    className="!h-[13px] shrink-0 text-right"
                  />
                  <SkeletonLine
                    width="w-12"
                    className="!h-[13px] shrink-0 text-right font-bold"
                  />
                  <SkeletonLine
                    width="w-10"
                    className="!h-[10px] !rounded-full shrink-0 text-center"
                  />
                </div>
              ))}
            </div>
          </div>

          {/* Tablet rows skeleton (sm -> lg) — matches TabletRow structure */}
          <div className="hidden sm:block lg:hidden">
            <div className="space-y-2">
              {Array.from({ length: PANEL_ROW_SKELETON_COUNT }).map((_, i) => (
                <div
                  key={i}
                  className="usage-surface flex items-center gap-3 rounded-xl px-3.5 py-3"
                  style={{ borderColor: "var(--usage-border)" }}
                >
                  {/* Time + duration block */}
                  <div className="w-24 shrink-0 space-y-1">
                    <SkeletonLine
                      width={i % 2 === 0 ? "w-20" : "w-16"}
                      className="!h-[12px]"
                    />
                    <SkeletonLine
                      width="w-10"
                      className="!h-[10px] !opacity-50"
                    />
                  </div>
                  {/* Model + status + agent block */}
                  <div className="min-w-0 flex-1 space-y-1">
                    <div className="flex items-center gap-2">
                      <SkeletonLine
                        width={i % 3 === 0 ? "w-24" : "w-20"}
                        className="!h-[12px]"
                      />
                      <SkeletonLine
                        width="w-8"
                        className="!h-[10px] !rounded-full shrink-0"
                      />
                    </div>
                    <SkeletonLine
                      width="w-14"
                      className="!h-[10px] !opacity-40"
                    />
                  </div>
                  {/* Token numbers */}
                  <div className="flex items-center gap-2.5 shrink-0">
                    <SkeletonLine width="w-8" className="!h-[12px]" />
                    <SkeletonLine width="w-8" className="!h-[12px]" />
                    <SkeletonLine
                      width="w-10"
                      className="!h-[12px] font-bold"
                    />
                  </div>
                  {/* Admin avatar */}
                  <div
                    className="skeleton-line h-7 w-7 shrink-0 rounded-full"
                    style={{
                      backgroundColor:
                        "var(--usage-icon-bg, var(--glass-bg-subtle))",
                    }}
                  />
                </div>
              ))}
            </div>
          </div>

          {/* Mobile card skeleton (< sm) — matches MobileCard structure */}
          <div className="space-y-4 pb-5 sm:hidden">
            {Array.from({ length: PANEL_ROW_SKELETON_COUNT }).map((_, i) => (
              <div
                key={i}
                className="usage-surface usage-mobile-card overflow-hidden rounded-2xl"
              >
                <div className="px-4 pt-4 pb-3.5">
                  {/* Header: icon + model info + status */}
                  <div className="flex items-start justify-between gap-2">
                    <div className="flex min-w-0 flex-1 items-center gap-2.5">
                      {/* 40×40 icon box matching MobileCard */}
                      <div
                        className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl"
                        style={{
                          backgroundColor:
                            "var(--usage-icon-bg, var(--glass-bg-subtle))",
                        }}
                      >
                        <div className="skeleton-line size-4 rounded-sm" />
                      </div>
                      <div className="min-w-0 flex-1">
                        <SkeletonLine
                          width={i % 2 === 0 ? "w-28" : "w-20"}
                          className="!h-[13px]"
                        />
                        {/* Agent + persona pills in flex-wrap */}
                        <div className="mt-2 flex flex-wrap items-center gap-1.5">
                          <SkeletonLine
                            width={i % 2 === 0 ? "w-12" : "w-16"}
                            className="!h-[10px] !rounded-full"
                          />
                          {i % 2 === 0 && (
                            <SkeletonLine
                              width="w-14"
                              className="!h-[10px] !rounded-full !opacity-50"
                            />
                          )}
                        </div>
                      </div>
                    </div>
                    {/* Status pill */}
                    <SkeletonLine
                      width="w-10"
                      className="!h-[10px] !rounded-full shrink-0"
                    />
                  </div>

                  {/* Token metrics — 4-col segmented bar matching MobileCard usage-metrics-bar */}
                  <div
                    className="usage-metrics-bar mt-4 grid grid-cols-4 overflow-hidden rounded-xl"
                    style={{
                      backgroundColor:
                        "var(--usage-inset-bg, var(--glass-bg-subtle))",
                    }}
                  >
                    {[0, 1, 2, 3].map((j) => (
                      <div
                        key={j}
                        className={`flex flex-col items-center py-2.5 ${
                          j > 0 ? "border-l border-[var(--usage-border)]" : ""
                        }`}
                      >
                        <SkeletonLine
                          width="w-6"
                          className="!h-[8px] !opacity-60"
                        />
                        <SkeletonLine width="w-8" className="!h-[14px] mt-1" />
                      </div>
                    ))}
                  </div>

                  {/* Metadata footer — clock icon + time / username + duration */}
                  <div className="mt-3 flex items-center justify-between">
                    <div className="flex min-w-0 items-center gap-1">
                      <div className="skeleton-line size-[9px] rounded shrink-0 !opacity-40" />
                      <SkeletonLine
                        width="w-20"
                        className="!h-[10px] !opacity-40"
                      />
                    </div>
                    <div className="flex shrink-0 items-center gap-2">
                      <SkeletonLine
                        width="w-8"
                        className="!h-[10px] !opacity-40"
                      />
                      <SkeletonLine
                        width="w-6"
                        className="!h-[10px] !opacity-40"
                      />
                    </div>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </>

        {/* 9. Pagination */}
      </div>
      <PanelPaginationSkeleton />
    </div>
  );
}
