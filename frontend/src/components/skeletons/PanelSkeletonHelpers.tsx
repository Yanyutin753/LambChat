import { SkeletonLine } from "./primitives";

export const PANEL_CARD_SKELETON_COUNT = 24;

type PanelPaginationVariant = "default" | "wide" | "compact" | "transparent";

const panelPaginationClasses: Record<PanelPaginationVariant, string> = {
  default: "glass-divider px-3 py-3 sm:px-4 mt-2",
  wide: "glass-divider px-3 py-3 sm:px-6 mt-2",
  compact: "glass-divider px-3 py-3 mt-2",
  transparent: "glass-divider bg-transparent px-4 py-4 sm:px-6 mt-2",
};

export function PanelPaginationSkeleton({
  variant = "default",
}: {
  variant?: PanelPaginationVariant;
}) {
  return (
    <div className={panelPaginationClasses[variant]}>
      <div className="flex items-center justify-center gap-2">
        <div className="skeleton-line size-8 rounded-lg" />
        <div className="skeleton-line w-32 sm:w-36 h-3" />
        <div className="skeleton-line size-8 rounded-lg" />
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
    <div className="inline-grid grid-cols-2 rounded-lg border border-[var(--glass-border)] bg-[var(--glass-bg-subtle)] p-1 my-3">
      <div className={panelSegmentedTabItemClass}>
        <SkeletonLine width={activeWidth} className="!h-4" />
      </div>
      <div className={panelSegmentedTabItemClass}>
        <SkeletonLine width={inactiveWidth} className="!h-4 !opacity-50" />
      </div>
    </div>
  );
}
