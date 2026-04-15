/**
 * Reusable skeleton loading components for modals and panels.
 * Uses the existing `.skeleton-line` CSS class with shimmer animation.
 */

interface SkeletonLineProps {
  width?: string;
  className?: string;
}

export function SkeletonLine({
  width = "w-full",
  className = "",
}: SkeletonLineProps) {
  return (
    <div className={`skeleton-line h-3 rounded-full ${width} ${className}`} />
  );
}

interface SkeletonBlockProps {
  width?: string;
  height?: string;
  className?: string;
}

export function SkeletonBlock({
  width = "w-full",
  height = "h-10",
  className = "",
}: SkeletonBlockProps) {
  return (
    <div
      className={`skeleton-line rounded-lg ${width} ${height} ${className}`}
    />
  );
}

interface SkeletonListProps {
  count?: number;
  className?: string;
}

export function SkeletonList({ count = 4, className = "" }: SkeletonListProps) {
  return (
    <div className={`space-y-2 sm:space-y-3 ${className}`}>
      {Array.from({ length: count }).map((_, i) => (
        <div
          key={i}
          className="flex items-center gap-2.5 sm:gap-3 px-2.5 sm:px-3 py-1.5 sm:py-2"
        >
          <div className="skeleton-line h-3.5 sm:h-4 w-3.5 sm:w-4 rounded-full flex-shrink-0" />
          <div className="flex-1 space-y-1 sm:space-y-1.5">
            <SkeletonLine width={i % 2 === 0 ? "w-3/4" : "w-1/2"} />
            <SkeletonLine width="w-1/3" className="!h-1.5 sm:!h-2" />
          </div>
        </div>
      ))}
    </div>
  );
}

interface SkeletonCardProps {
  className?: string;
}

export function SkeletonCard({ className = "" }: SkeletonCardProps) {
  return (
    <div
      className={`p-2.5 sm:p-3 rounded-lg bg-stone-50 dark:bg-stone-900/50 border border-stone-200 dark:border-stone-700 ${className}`}
    >
      <div className="flex items-center gap-2 mb-1.5 sm:mb-2">
        <SkeletonBlock
          width="w-4 sm:w-5"
          height="h-4 sm:h-5"
          className="!rounded-full"
        />
        <SkeletonLine width="w-20 sm:w-24" />
        <SkeletonLine width="w-14 sm:w-16" className="ml-auto" />
      </div>
      <SkeletonLine width="w-full" className="!h-1.5 sm:!h-2" />
    </div>
  );
}
