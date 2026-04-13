import { SkeletonLine } from "./primitives";

/** Matches PanelHeader layout: icon box + title + optional search + actions */
export function PanelHeaderSkeleton({
  hasSearch = true,
}: {
  hasSearch?: boolean;
}) {
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <div className="skeleton-line size-10 rounded-xl" />
          <div>
            <SkeletonLine width="w-32" className="!h-[18px]" />
            <SkeletonLine width="w-48" className="!h-3.5 mt-1" />
          </div>
        </div>
        <div className="flex items-center gap-2">
          <div className="skeleton-line h-9 w-20 rounded-lg" />
          <div className="skeleton-line h-9 w-20 rounded-lg" />
        </div>
      </div>
      {hasSearch && (
        <div className="flex items-center gap-2">
          <div className="skeleton-line h-10 flex-1 rounded-lg" />
        </div>
      )}
    </div>
  );
}
