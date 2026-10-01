import { SkeletonLine } from "./primitives";

export const PANEL_CARD_SKELETON_COUNT = 24;
export const PANEL_ROW_SKELETON_COUNT = 24;

/** Uses the same footer and responsive controls as Pagination. */
export function PanelPaginationSkeleton() {
  return (
    <div className="panel-pagination" aria-hidden="true">
      <div className="pagination-wrapper">
        <div className="pagination-summary">
          <SkeletonLine width="w-36" className="pagination-range !h-3" />
          <SkeletonLine width="w-12" className="pagination-position !h-3" />
        </div>
        <div className="pagination-controls">
          <div className="pagination-btn skeleton-line" />
          {[0, 1, 2].map((page) => (
            <div key={page} className="pagination-page skeleton-line" />
          ))}
          <div className="pagination-btn skeleton-line" />
        </div>
      </div>
    </div>
  );
}

const panelSegmentedTabItemClass =
  "flex items-center justify-center gap-2 rounded-md px-3 py-2";

export function PanelSegmentedTabsSkeleton({
  activeWidth,
  inactiveWidth,
}: {
  activeWidth: string;
  inactiveWidth: string;
}) {
  return (
    <div className="inline-grid grid-cols-2 rounded-lg border border-[var(--glass-border)] bg-[var(--glass-bg-subtle)] p-1 my-3 font-sans">
      <div className={panelSegmentedTabItemClass}>
        <SkeletonLine width={activeWidth} className="!h-4" />
      </div>
      <div className={panelSegmentedTabItemClass}>
        <SkeletonLine width={inactiveWidth} className="!h-4 !opacity-50" />
      </div>
    </div>
  );
}
