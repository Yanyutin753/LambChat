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
  /** Single-line variant that matches search result item height */
  compact?: boolean;
}

export function SkeletonList({
  count = 4,
  className = "",
  compact = false,
}: SkeletonListProps) {
  return (
    <div
      className={
        compact
          ? `space-y-0 ${className}`
          : `space-y-1.5 sm:space-y-2.5 ${className}`
      }
    >
      {Array.from({ length: count }).map((_, i) => (
        <div
          key={i}
          className={`flex items-center gap-3 px-4 rounded-lg ${
            compact
              ? "py-2.5"
              : "px-2 sm:px-3 py-2 sm:py-2.5 sm:gap-3 sm:rounded-xl"
          }`}
          style={{
            backgroundColor:
              i === 0
                ? "var(--theme-bg-card, color-mix(in srgb, var(--theme-bg) 80%, white))"
                : undefined,
          }}
        >
          {compact ? (
            <SkeletonLine width={i % 2 === 0 ? "w-3/4" : "w-1/2"} />
          ) : (
            <>
              <div className="skeleton-line h-4 sm:h-[18px] w-4 sm:w-[18px] rounded-full flex-shrink-0" />
              <div className="flex-1 space-y-1 sm:space-y-1.5 min-w-0">
                <SkeletonLine width={i % 2 === 0 ? "w-3/4" : "w-1/2"} />
                <SkeletonLine
                  width="w-1/3"
                  className="!h-1.5 sm:!h-2 !opacity-60"
                />
              </div>
            </>
          )}
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
      className={`p-2.5 sm:p-3 rounded-lg border ${className}`}
      style={{
        backgroundColor:
          "var(--theme-bg-card, color-mix(in srgb, var(--theme-bg) 80%, white))",
        borderColor: "var(--theme-border)",
      }}
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
