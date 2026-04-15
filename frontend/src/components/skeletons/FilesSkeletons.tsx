import { SkeletonLine } from "./primitives";
import { SidebarSkeleton } from "./SidebarSkeleton";

/** Files content area skeleton (toolbar + grid cards, no sidebar/header) */
export function FilesContentSkeleton() {
  return (
    <div className="flex min-h-full flex-col animate-fade-in">
      {/* Toolbar skeleton */}
      <div className="sticky top-0 z-10">
        <div
          className="absolute inset-0"
          style={{ backgroundColor: "var(--theme-bg)" }}
        />
        <div className="absolute bottom-0 left-0 right-0 h-px bg-stone-200/60 dark:bg-stone-700/40" />
        <div className="relative px-3 sm:px-5 md:px-6 py-2.5 sm:py-3 md:py-4">
          <div className="flex items-center justify-between gap-2 sm:gap-3 w-full">
            <div className="flex flex-wrap gap-1.5 sm:gap-2 items-center">
              <div className="skeleton-line h-7 sm:h-8 w-16 sm:w-20 rounded-lg" />
              <div className="skeleton-line h-7 sm:h-8 w-14 sm:w-16 rounded-lg" />
              <div className="skeleton-line h-7 sm:h-8 w-20 sm:w-24 rounded-lg hidden md:block" />
              <div className="skeleton-line h-7 sm:h-8 w-16 sm:w-20 rounded-lg" />
            </div>
            <div className="flex items-center gap-1.5 sm:gap-2 shrink-0">
              <div className="skeleton-line h-8 sm:h-9 w-[120px] sm:w-[160px] md:w-[200px] rounded-lg" />
              <div className="skeleton-line h-7 sm:h-8 w-14 sm:w-16 rounded-lg hidden md:block" />
            </div>
          </div>
        </div>
      </div>

      {/* Content: session groups with grid cards */}
      <div className="flex-1 overflow-y-auto min-h-0 relative z-[1]">
        <div className="flex flex-col pb-6 px-3 sm:px-5 md:px-6 gap-3 md:gap-6">
          {/* Session group 1 */}
          <div className="flex flex-col gap-2.5 md:gap-3">
            <div className="flex items-center justify-between gap-2 pt-3 sm:pt-4 md:pt-5">
              <SkeletonLine
                width="w-32 sm:w-40"
                className="!h-[14px] sm:!h-[15px] !rounded-md"
              />
              <div className="skeleton-line h-[16px] sm:h-[18px] w-8 sm:w-10 rounded-md" />
            </div>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-2.5 sm:gap-3 items-start">
              {[0, 1, 2].map((i) => (
                <div
                  key={i}
                  className="flex flex-col overflow-hidden rounded-xl border border-stone-200/60 dark:border-stone-700/40"
                  style={{ backgroundColor: "var(--theme-bg-card, #fff)" }}
                >
                  <div className="flex items-center gap-2 px-2 sm:px-2.5 py-2 sm:py-2.5 border-b border-stone-100 dark:border-stone-800/80">
                    <div className="skeleton-line size-3.5 sm:size-4 rounded shrink-0" />
                    <SkeletonLine
                      width={i === 0 ? "w-3/4" : i === 1 ? "w-1/2" : "w-2/3"}
                      className="!h-[12px] sm:!h-[13px] flex-1"
                    />
                    <div className="skeleton-line size-6 sm:size-7 rounded-md shrink-0" />
                  </div>
                  <div className="aspect-[16/9] bg-stone-50/80 dark:bg-stone-800/20 flex items-center justify-center">
                    <div className="skeleton-line size-6 sm:size-8 rounded-lg" />
                  </div>
                  <div className="px-2 sm:px-2.5 py-1.5 sm:py-2">
                    <SkeletonLine
                      width={i === 0 ? "w-1/2" : "w-2/5"}
                      className="!h-[10px] sm:!h-[11px]"
                    />
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Session group 2 */}
          <div className="flex flex-col gap-2.5 md:gap-3">
            <div className="flex items-center justify-between gap-2 pt-3 sm:pt-4 md:pt-5">
              <SkeletonLine
                width="w-24 sm:w-32"
                className="!h-[14px] sm:!h-[15px] !rounded-md"
              />
              <div className="skeleton-line h-[16px] sm:h-[18px] w-8 sm:w-10 rounded-md" />
            </div>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-2.5 sm:gap-3 items-start">
              {[0, 1].map((i) => (
                <div
                  key={i}
                  className="flex flex-col overflow-hidden rounded-xl border border-stone-200/60 dark:border-stone-700/40"
                  style={{ backgroundColor: "var(--theme-bg-card, #fff)" }}
                >
                  <div className="flex items-center gap-2 px-2 sm:px-2.5 py-2 sm:py-2.5 border-b border-stone-100 dark:border-stone-800/80">
                    <div className="skeleton-line size-3.5 sm:size-4 rounded shrink-0" />
                    <SkeletonLine
                      width={i === 0 ? "w-3/5" : "w-4/5"}
                      className="!h-[12px] sm:!h-[13px] flex-1"
                    />
                    <div className="skeleton-line size-6 sm:size-7 rounded-md shrink-0" />
                  </div>
                  <div className="aspect-[16/9] bg-stone-50/80 dark:bg-stone-800/20 flex items-center justify-center">
                    <div className="skeleton-line size-6 sm:size-8 rounded-lg" />
                  </div>
                  <div className="px-2 sm:px-2.5 py-1.5 sm:py-2">
                    <SkeletonLine
                      width="w-1/3"
                      className="!h-[10px] sm:!h-[11px]"
                    />
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

/** Full page skeleton for the files/document library (sidebar + header + content) */
export function FilesPageSkeleton() {
  return (
    <div
      className="flex h-[100dvh] w-full overflow-hidden animate-fade-in"
      style={{ backgroundColor: "var(--theme-bg)" }}
    >
      <SidebarSkeleton />

      <div className="relative flex flex-1 min-w-0 flex-col overflow-hidden">
        {/* Header skeleton */}
        <div
          className="flex items-center justify-between px-3 sm:px-4 py-2.5 sm:py-3 border-b shrink-0"
          style={{ borderColor: "var(--theme-border)" }}
        >
          <div className="flex items-center gap-2 sm:gap-3">
            <div className="skeleton-line size-5 rounded-full shrink-0" />
            <div className="skeleton-line h-3.5 sm:h-4 w-20 sm:w-28 rounded-md" />
          </div>
          <div className="flex items-center gap-1.5 sm:gap-2">
            <div className="skeleton-line size-7 sm:size-8 rounded-full" />
            <div className="skeleton-line size-7 sm:size-8 rounded-full" />
          </div>
        </div>

        <main className="flex-1 overflow-hidden">
          <div className="w-full h-full sm:mx-auto sm:max-w-3xl xl:sm:max-w-5xl">
            <FilesContentSkeleton />
          </div>
        </main>
      </div>
    </div>
  );
}
