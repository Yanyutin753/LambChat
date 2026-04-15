import { SkeletonLine } from "./primitives";

/** Matches PanelHeader layout: icon box + title + optional search + actions */
export function PanelHeaderSkeleton({
  hasSearch = true,
}: {
  hasSearch?: boolean;
}) {
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2 sm:gap-3">
        <div className="flex items-center gap-2.5 sm:gap-3 min-w-0">
          <div className="skeleton-line size-8 sm:size-10 rounded-xl shrink-0" />
          <div className="min-w-0">
            <SkeletonLine
              width="w-24 sm:w-32"
              className="!h-[16px] sm:!h-[18px]"
            />
            <SkeletonLine
              width="w-36 sm:w-48"
              className="!h-3 sm:!h-3.5 mt-1"
            />
          </div>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          <div className="skeleton-line h-8 sm:h-9 w-16 sm:w-20 rounded-lg" />
          <div className="skeleton-line h-8 sm:h-9 w-16 sm:w-20 rounded-lg" />
        </div>
      </div>
      {hasSearch && (
        <div className="flex items-center gap-2">
          <div className="skeleton-line h-9 sm:h-10 flex-1 rounded-lg" />
        </div>
      )}
    </div>
  );
}
