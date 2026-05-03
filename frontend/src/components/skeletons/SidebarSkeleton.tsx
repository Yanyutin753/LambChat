import { SIDEBAR_COLLAPSED_STORAGE_KEY } from "../../hooks/useAuth";

/** Sidebar skeleton — matches real SessionSidebar layout */
export function SidebarSkeleton() {
  const collapsed = (() => {
    const saved = localStorage.getItem(SIDEBAR_COLLAPSED_STORAGE_KEY);
    return saved !== null ? saved === "true" : true;
  })();

  if (collapsed) {
    return <SidebarRailSkeleton />;
  }

  return <SidebarExpandedSkeleton />;
}

/** Skeleton for the collapsed sidebar rail */
function SidebarRailSkeleton() {
  return (
    <div
      className="hidden sm:flex h-full relative shrink-0 overflow-hidden"
      style={{ width: "var(--sidebar-rail-width)" }}
    >
      <nav className="absolute inset-0 flex h-full w-full flex-col items-start bg-[var(--theme-bg-sidebar)] border-r border-stone-200/60 dark:border-stone-800/60">
        {/* Expand button area */}
        <div className="h-11 flex items-center justify-center w-full pt-3">
          <div className="skeleton-line size-9 rounded-lg mx-2" />
        </div>

        {/* Action icons */}
        <div className="mt-3 flex flex-col items-center w-full gap-px space-y-1">
          <div className="skeleton-line size-9 rounded-lg mx-2" />
          <div className="skeleton-line size-9 rounded-lg mx-2" />
          <div className="skeleton-line size-9 rounded-lg mx-2" />
          <div className="skeleton-line size-9 rounded-lg mx-2" />
        </div>

        <div className="flex-grow" />

        {/* Profile avatar */}
        <div className="shrink-0 px-2 py-4 border-t border-stone-200/60 dark:border-stone-800/60">
          <div className="flex items-center justify-center w-full py-[11px]">
            <div className="skeleton-line size-8 rounded-full shrink-0" />
          </div>
        </div>
      </nav>
    </div>
  );
}

/** Skeleton for the expanded sidebar */
function SidebarExpandedSkeleton() {
  return (
    <div
      className="hidden sm:flex w-64 shrink-0 flex-col rounded-r-lg overflow-hidden"
      style={{
        borderRight:
          "1px solid color-mix(in srgb, var(--theme-border) 60%, transparent)",
        backgroundColor: "color-mix(in srgb, var(--theme-bg) 50%, transparent)",
      }}
    >
      {/* Header area — app icon + name + collapse button */}
      <div className="flex items-center justify-between px-3 pt-3 pb-1 sm:px-4">
        <div className="flex items-center gap-2">
          <div className="skeleton-line size-6 rounded-full shrink-0" />
          <div className="skeleton-line h-[18px] w-20 rounded-md" />
        </div>
        <div className="skeleton-line size-8 rounded-lg shrink-0" />
      </div>

      {/* Action buttons — New Chat, Search, File Library */}
      <div className="flex flex-col gap-px px-2 py-2 space-y-1">
        {/* New Chat */}
        <div className="w-full h-9 rounded-[10px] flex items-center gap-3 px-[9px]">
          <div className="skeleton-line size-[18px] rounded-md shrink-0" />
          <div className="skeleton-line h-3.5 w-16 rounded-md" />
        </div>
        {/* Search with badge */}
        <div className="w-full h-9 rounded-[10px] flex items-center gap-3 px-[9px]">
          <div className="skeleton-line size-[18px] rounded-md shrink-0" />
          <div className="skeleton-line h-3.5 w-14 rounded-md flex-1" />
          <div className="skeleton-line h-4 w-10 rounded-md" />
        </div>
        {/* File Library */}
        <div className="w-full h-9 rounded-[10px] flex items-center gap-3 px-[9px]">
          <div className="skeleton-line size-[18px] rounded-md shrink-0" />
          <div className="skeleton-line h-3.5 w-20 rounded-md" />
        </div>
      </div>

      {/* Session list */}
      <div className="flex-1 overflow-hidden px-2 space-y-px">
        {/* Section header — Projects */}
        <div className="flex items-center justify-between px-[9px] h-9">
          <div className="skeleton-line h-3 w-16 rounded-md" />
          <div className="skeleton-line size-3.5 rounded-sm shrink-0" />
        </div>
        {/* Project group */}
        <div className="space-y-px">
          {[0, 1, 2].map((i) => (
            <div
              key={i}
              className="flex items-center gap-3 px-[9px] h-10 rounded-[10px]"
            >
              <div className="skeleton-line size-[18px] rounded shrink-0" />
              <div
                className="skeleton-line h-[13px] rounded-md flex-1"
                style={{ width: i === 0 ? "75%" : i === 1 ? "60%" : "85%" }}
              />
            </div>
          ))}
        </div>

        {/* Section header — Chats */}
        <div className="mt-2 flex items-center justify-between px-[9px] h-9">
          <div className="skeleton-line h-3 w-12 rounded-md" />
          <div className="skeleton-line size-3.5 rounded-sm shrink-0" />
        </div>
        {/* Chat items */}
        <div className="space-y-px">
          {[0, 1, 2, 3].map((i) => (
            <div
              key={i}
              className="flex items-center gap-2 px-[9px] h-10 rounded-[10px]"
            >
              <div
                className="skeleton-line h-[13px] rounded-md flex-1"
                style={{
                  width:
                    i === 0 ? "70%" : i === 1 ? "85%" : i === 2 ? "55%" : "65%",
                }}
              />
            </div>
          ))}
        </div>
      </div>

      {/* Bottom user area */}
      <div className="shrink-0 px-2 py-1 border-t border-stone-200/60 dark:border-stone-800/60">
        <div className="flex items-center gap-3 px-2 py-3 rounded-xl">
          <div className="skeleton-line size-8 rounded-full shrink-0" />
          <div className="skeleton-line h-3.5 w-16 rounded-md" />
        </div>
      </div>
    </div>
  );
}
