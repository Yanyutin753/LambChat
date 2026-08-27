import { SkeletonLine } from "./primitives";
import { PANEL_ROW_SKELETON_COUNT } from "./PanelSkeletonHelpers";
import { SidebarSkeleton } from "./SidebarSkeleton";

const appSafeAreaTop =
  "max(var(--app-safe-area-top, 0px), var(--app-fullscreen-safe-area-top, 0px))";
const appSafeAreaBottom =
  "max(var(--app-safe-area-bottom, 0px), var(--app-fullscreen-safe-area-bottom, 0px))";

/** Toolbar skeleton — only for page-level fallback where no real Toolbar is mounted */
function FilesToolbarSkeleton() {
  return (
    <div className="sticky top-0 z-10">
      <div
        className="absolute inset-0"
        style={{ backgroundColor: "var(--theme-bg)" }}
      />
      <div className="absolute bottom-0 left-0 right-0 h-px bg-theme-border/60" />
      <div className="relative px-3 @sm:px-4 @md:px-6 py-2 @md:py-3">
        <div className="flex items-center justify-between gap-2 @sm:gap-3 w-full font-serif">
          <div className="flex flex-wrap gap-1.5 sm:gap-2 items-center">
            <div className="skeleton-line h-9 w-16 sm:w-20 rounded-lg" />
            <div className="skeleton-line h-9 w-14 rounded-lg" />
            <div className="skeleton-line h-9 w-20 sm:w-24 rounded-lg hidden @lg:block" />
            <div className="skeleton-line h-9 w-14 rounded-lg" />
          </div>
          <div className="flex items-center gap-1.5 sm:gap-2 shrink-0">
            <div className="skeleton-line h-9 w-[120px] @sm:w-[160px] @md:w-[200px] rounded-lg" />
            <div className="skeleton-line h-9 w-9 rounded-lg hidden @sm:block" />
          </div>
        </div>
      </div>
    </div>
  );
}

/** Session group list skeleton — content only, the real Toolbar stays mounted above it */
export function FilesListSkeleton() {
  return (
    <div className="flex flex-col pb-6 px-4 @md:px-6 gap-3 @md:gap-6 animate-fade-in">
      {/* Session group 1 */}
      <div className="w-full flex flex-col gap-2.5 @md:gap-3">
        <div className="flex items-center justify-between gap-2 pt-4 @md:pt-5 font-serif">
          <SkeletonLine
            width="w-32 sm:w-40"
            className="!h-[14px] sm:!h-[15px] !rounded-md"
          />
          <div className="skeleton-line h-[16px] sm:h-[18px] w-8 sm:w-10 rounded-md" />
        </div>
        <div className="grid auto-grid-cols gap-3 items-start">
          {Array.from({ length: PANEL_ROW_SKELETON_COUNT }).map((_, i) => (
            <FileCardSkeleton key={i} i={i} />
          ))}
        </div>
      </div>

      {/* Session group 2 */}
      <div className="w-full flex flex-col gap-2.5 @md:gap-3">
        <div className="flex items-center justify-between gap-2 pt-4 @md:pt-5 font-serif">
          <SkeletonLine
            width="w-24 sm:w-32"
            className="!h-[14px] sm:!h-[15px] !rounded-md"
          />
          <div className="skeleton-line h-[16px] sm:h-[18px] w-8 sm:w-10 rounded-md" />
        </div>
        <div className="grid auto-grid-cols gap-3 items-start">
          {Array.from({ length: PANEL_ROW_SKELETON_COUNT }).map((_, i) => (
            <FileCardSkeleton key={i} i={i} />
          ))}
        </div>
      </div>
    </div>
  );
}

/** Files content area skeleton (toolbar + grid cards, no sidebar/header) */
export function FilesContentSkeleton() {
  return (
    <div className="flex min-h-full flex-col @container animate-fade-in">
      <FilesToolbarSkeleton />
      <div className="flex-1 overflow-y-auto min-h-0 relative z-[1]">
        <FilesListSkeleton />
      </div>
    </div>
  );
}

/** Single file card skeleton — matches GridCard structure */
function FileCardSkeleton({ i }: { i: number }) {
  return (
    <div className="flex flex-col overflow-hidden rounded-xl border border-theme-border bg-theme-bg-card">
      {/* File header — no border-b in real GridCard */}
      <div className="flex items-center gap-2 px-2.5 py-2.5">
        <div className="skeleton-line size-4 rounded shrink-0" />
        <SkeletonLine
          width={i === 0 ? "w-3/4" : i === 1 ? "w-1/2" : "w-2/3"}
          className="!h-[12px] sm:!h-[13px] flex-1"
        />
        <div className="skeleton-line size-7 rounded-md shrink-0" />
      </div>
      {/* Preview area — uses theme bg */}
      <div className="aspect-[16/9] bg-theme-bg-subtle flex items-center justify-center">
        <div className="skeleton-line size-8 rounded-lg" />
      </div>
      {/* Meta footer */}
      <div className="px-2.5 py-2">
        <SkeletonLine
          width={i === 0 ? "w-1/2" : "w-2/5"}
          className="!h-[10px] sm:!h-[11px]"
        />
      </div>
    </div>
  );
}

/** Full page skeleton for the files/document library (sidebar + header + content) */
export function FilesPageSkeleton() {
  return (
    <div
      className="flex h-[100dvh] w-full overflow-hidden animate-fade-in"
      style={{
        backgroundColor: "var(--theme-bg)",
        boxSizing: "content-box",
        paddingTop: appSafeAreaTop,
        paddingBottom: appSafeAreaBottom,
        height: `calc(100dvh - ${appSafeAreaTop} - ${appSafeAreaBottom})`,
      }}
    >
      <SidebarSkeleton />

      <div className="relative flex flex-1 min-w-0 flex-col overflow-hidden">
        {/* Header skeleton */}
        <header className="relative z-50 flex items-center px-3 sm:px-5 py-3 shrink-0 rounded-bl-xl">
          <div className="flex items-center gap-1.5 flex-shrink-0">
            <div className="skeleton-line size-8 rounded-lg" />
            <div className="skeleton-line h-4 w-24 sm:w-28 rounded-md" />
          </div>
          <div className="flex-1" />
          <div className="flex items-center gap-1.5 sm:gap-2 flex-shrink-0">
            <div className="skeleton-line size-8 rounded-lg" />
            <div className="skeleton-line size-8 rounded-lg" />
          </div>
        </header>

        <main className="flex-1 overflow-hidden">
          <div className="w-full h-full sm:mx-auto lg:max-w-[80rem] xl:max-w-[96rem] 2xl:max-w-[120rem] px-4">
            <FilesContentSkeleton />
          </div>
        </main>
      </div>
    </div>
  );
}
