/** Sidebar skeleton shared by chat and files page skeletons */
export function SidebarSkeleton() {
  return (
    <div
      className="hidden sm:flex w-[260px] shrink-0 flex-col border-r overflow-hidden"
      style={{
        borderColor: "var(--theme-border)",
        backgroundColor: "color-mix(in srgb, var(--theme-bg) 50%, transparent)",
      }}
    >
      {/* Top action buttons */}
      <div className="px-2 pt-3 pb-2 space-y-1">
        <div className="w-full h-9 rounded-[10px] flex items-center gap-3 px-[9px]">
          <div className="skeleton-line size-[18px] rounded-md shrink-0" />
          <div className="skeleton-line h-3.5 w-16 rounded-md" />
        </div>
        <div className="w-full h-9 rounded-[10px] flex items-center gap-3 px-[9px]">
          <div className="skeleton-line size-[18px] rounded-md shrink-0" />
          <div className="skeleton-line h-3.5 w-24 rounded-md flex-1" />
          <div className="skeleton-line h-4 w-10 rounded-md" />
        </div>
      </div>

      {/* Session list skeleton */}
      <div className="flex-1 overflow-hidden px-2 space-y-px">
        <div className="flex items-center justify-between px-[9px] h-9">
          <div className="skeleton-line h-3 w-14 rounded-md" />
        </div>
        {/* Project group 1 */}
        <div className="space-y-px">
          <div className="flex items-center gap-2 px-[9px] h-8">
            <div className="skeleton-line size-3.5 rounded-sm shrink-0" />
            <div className="skeleton-line h-3 w-20 rounded-md" />
          </div>
          {[0, 1, 2].map((i) => (
            <div
              key={i}
              className="flex items-center gap-2 px-[9px] h-9 rounded-lg"
            >
              <div className="skeleton-line size-4 rounded-full shrink-0" />
              <div className="flex-1 min-w-0">
                <div
                  className="skeleton-line h-3 rounded-md"
                  style={{ width: i === 0 ? "75%" : i === 1 ? "60%" : "85%" }}
                />
              </div>
            </div>
          ))}
        </div>
        {/* Project group 2 */}
        <div className="mt-2 space-y-px">
          <div className="flex items-center gap-2 px-[9px] h-8">
            <div className="skeleton-line size-3.5 rounded-sm shrink-0" />
            <div className="skeleton-line h-3 w-16 rounded-md" />
          </div>
          {[0, 1].map((i) => (
            <div
              key={i}
              className="flex items-center gap-2 px-[9px] h-9 rounded-lg"
            >
              <div className="skeleton-line size-4 rounded-full shrink-0" />
              <div
                className="skeleton-line h-3 rounded-md flex-1"
                style={{ width: i === 0 ? "70%" : "55%" }}
              />
            </div>
          ))}
        </div>
      </div>

      {/* Bottom user area */}
      <div
        className="px-2 py-2 border-t"
        style={{ borderColor: "var(--theme-border)" }}
      >
        <div className="flex items-center gap-2.5 px-[9px] h-10 rounded-lg">
          <div className="skeleton-line size-7 rounded-full shrink-0" />
          <div className="flex-1 space-y-1">
            <div className="skeleton-line h-3 w-16 rounded-md" />
            <div className="skeleton-line h-2 w-24 rounded-md !opacity-50" />
          </div>
        </div>
      </div>
    </div>
  );
}
