/** Sidebar skeleton — matches real SessionSidebar layout (w-64, no circle icons on items) */
export function SidebarSkeleton() {
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
        <div className="flex items-center gap-1 px-[9px] h-9">
          <div className="skeleton-line h-3 w-16 rounded-md" />
          <div className="skeleton-line size-3.5 rounded-sm shrink-0" />
        </div>
        {/* Project group */}
        <div className="space-y-px">
          {[0, 1, 2].map((i) => (
            <div
              key={i}
              className="flex items-center gap-2 px-[9px] h-10 rounded-[10px]"
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
        <div className="mt-2 flex items-center gap-1 px-[9px] h-9">
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
      <div
        className="px-2 pb-2 pt-1"
        style={{
          borderTop:
            "1px solid color-mix(in srgb, var(--theme-border) 60%, transparent)",
        }}
      >
        <div className="flex items-center gap-2 px-[9px] h-10 rounded-[10px]">
          <div className="skeleton-line size-5 rounded-full shrink-0" />
          <div className="skeleton-line h-[14px] w-16 rounded-md" />
        </div>
      </div>
    </div>
  );
}
