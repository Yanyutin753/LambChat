import { SkeletonLine } from "./primitives";

/** Matches PanelHeader layout: icon box (size-12, gradient bg) + title + optional search + actions */
export function PanelHeaderSkeleton({
  hasSearch = true,
}: {
  hasSearch?: boolean;
}) {
  return (
    <div
      className="panel-header"
      style={{ borderBottomColor: "var(--theme-border)" }}
    >
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-3 min-w-0">
          {/* Icon box — matches real PanelHeader: size-12 rounded-xl gradient + shadow + ring */}
          <div
            className="size-12 shrink-0 rounded-xl shadow-sm ring-1 ring-stone-200/60 dark:ring-stone-700/50"
            style={{
              background:
                "linear-gradient(135deg, var(--theme-bg-card), color-mix(in srgb, var(--theme-bg) 70%, white))",
            }}
          >
            <div className="flex size-full items-center justify-center">
              <div className="skeleton-line size-6 rounded-md" />
            </div>
          </div>
          <div className="min-w-0">
            <SkeletonLine
              width="w-28 sm:w-36"
              className="!h-[18px] sm:!h-[20px]"
            />
            <SkeletonLine
              width="w-40 sm:w-52"
              className="!h-3 sm:!h-3.5 mt-0.5"
            />
          </div>
        </div>
        <div className="flex items-center gap-1.5 sm:gap-2 shrink-0">
          <div className="skeleton-line h-9 w-20 sm:w-24 rounded-lg" />
          <div className="skeleton-line h-9 w-9 rounded-lg sm:hidden" />
          <div className="skeleton-line h-9 w-20 sm:w-24 rounded-lg hidden sm:block" />
        </div>
      </div>
      {hasSearch && (
        <div className="flex items-center gap-2 mt-2 sm:mt-3">
          <div className="skeleton-line h-10 flex-1 rounded-lg" />
        </div>
      )}
    </div>
  );
}
