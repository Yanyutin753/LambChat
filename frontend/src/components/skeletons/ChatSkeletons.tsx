import { SkeletonLine } from "./primitives";
import { SidebarSkeleton } from "./SidebarSkeleton";

/** Full chat page skeleton: sidebar + header + chat messages + input */
export function ChatPageSkeleton() {
  return (
    <div
      className="flex h-[100dvh] w-full overflow-hidden animate-fade-in"
      style={{ backgroundColor: "var(--theme-bg)" }}
    >
      <SidebarSkeleton />

      {/* Main area */}
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

        {/* Welcome skeleton */}
        <main className="flex-1 overflow-hidden">
          <WelcomeSkeleton />
        </main>
      </div>
    </div>
  );
}

/** Skeleton that mimics a chat conversation layout (user + assistant alternating) */
export function ChatSkeleton({ count = 3 }: { count?: number }) {
  // Each entry: [bubble width, ...line widths] — mimics natural user queries of varying length
  const userMsgs = [
    { bubble: "w-[75%] sm:w-[55%]", lines: ["100%", "82%"] },
    { bubble: "w-[85%] sm:w-[65%]", lines: ["100%"] },
    { bubble: "w-[50%] sm:w-[35%]", lines: ["100%"] },
  ];

  return (
    <div className="animate-fade-in">
      {Array.from({ length: count }).map((_, i) => {
        const msg = userMsgs[i % userMsgs.length];
        return (
          <div key={i}>
            {/* ── User message ── matches UserMessageBubble structure exactly ── */}
            <div className="w-full px-2 py-1.5 sm:px-4 mb-3 sm:mb-4">
              <div className="mx-auto flex max-w-3xl xl:max-w-5xl justify-end px-2">
                <div
                  className={`flex flex-col items-end max-w-[90%] ${msg.bubble}`}
                >
                  <div
                    className="rounded-3xl w-full px-5 py-2.5 shadow-sm border"
                    style={{
                      background:
                        "linear-gradient(135deg, var(--theme-primary-light), var(--theme-bg))",
                      borderColor: "var(--theme-border)",
                    }}
                  >
                    <div className="leading-[1.625] text-[15px] sm:text-base space-y-1.5">
                      {msg.lines.map((w, li) => (
                        <SkeletonLine key={li} width={w} />
                      ))}
                    </div>
                  </div>
                </div>
              </div>
            </div>

            {/* ── Assistant response ── matches ChatMessage structure exactly ── */}
            <div className="group w-full mb-3 sm:mb-4">
              <div className="mx-auto flex flex-col max-w-3xl xl:max-w-5xl px-4 sm:px-6">
                <div className="min-w-0 min-h-0">
                  {/* Avatar + Role label — mb-3 gap-2 */}
                  <div className="mb-3 flex items-center gap-2">
                    <div className="skeleton-line size-6 rounded-full shrink-0" />
                    <SkeletonLine
                      width="w-16"
                      className="!h-[18px] sm:!h-[19px]"
                    />
                  </div>
                  {/* Thinking indicator — space-y-2.5 py-1 px-1, same as ThinkingIndicator */}
                  <div className="space-y-3 px-2 my-2">
                    <div className="skeleton-line w-full h-2 rounded-full" />
                    <div className="flex gap-3">
                      <div className="skeleton-line flex-1 h-2 rounded-full" />
                      <div className="skeleton-line flex-1 h-2 rounded-full" />
                      <div className="skeleton-line flex-1 h-2 rounded-full" />
                    </div>
                    <div className="flex gap-3">
                      <div className="skeleton-line flex-1 h-2 rounded-full" />
                      <div className="skeleton-line flex-1 h-2 rounded-full" />
                      <div className="skeleton-line flex-1 h-2 rounded-full" />
                    </div>
                    <div className="flex gap-3">
                      <div className="skeleton-line flex-1 h-2 rounded-full" />
                      <div className="skeleton-line w-2/5 h-2 rounded-full" />
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        );
      })}
    </div>
  );
}

/** Skeleton for the welcome page (greeting + input + suggestions) */
export function WelcomeSkeleton() {
  return (
    <div className="relative flex h-full flex-col items-center justify-center px-4 overflow-hidden animate-fade-in">
      {/* Greeting skeleton */}
      <div className="relative flex flex-col items-center mb-6 sm:mb-8 w-full max-w-[90vw]">
        {/* Mobile icon */}
        <div className="sm:hidden mb-4">
          <div className="skeleton-line size-12 rounded-2xl" />
        </div>
        {/* Greeting line */}
        <div className="max-w-[90vw] w-full flex items-center justify-center gap-3 sm:gap-4">
          <div className="skeleton-line size-10 sm:size-12 rounded-full hidden sm:block" />
          <SkeletonLine
            width="w-48 sm:w-64 lg:w-80"
            className="!h-7 sm:!h-8 lg:!h-10 !rounded-lg"
          />
        </div>
        {/* Subtitle */}
        <SkeletonLine
          width="w-36 sm:w-48"
          className="!h-3 sm:!h-4 mt-2 sm:mt-3 !rounded-lg"
        />
      </div>

      {/* Mobile: ChatInput skeleton */}
      <div className="w-full max-w-[48rem] sm:hidden mb-4">
        <div
          className="rounded-2xl px-1 py-1.5 space-y-1"
          style={{
            backgroundColor: "var(--theme-bg-card)",
            borderColor: "var(--theme-border)",
            border: "1px solid var(--theme-border)",
            boxShadow: "0 2px 12px rgba(0,0,0,0.06)",
          }}
        >
          <div className="px-3 py-1.5">
            <div className="skeleton-line h-3 w-3/5 rounded" />
          </div>
          <div className="flex items-center justify-between px-2 pb-1.5">
            <div className="flex items-center gap-2">
              <div className="skeleton-line size-7 rounded-full" />
              <div className="skeleton-line size-7 rounded-full" />
              <div className="skeleton-line size-7 rounded-full" />
            </div>
            <div className="skeleton-line size-7 rounded-full" />
          </div>
        </div>
      </div>

      {/* Desktop: ChatInput skeleton */}
      <div className="w-full max-w-[48rem] hidden sm:block">
        <div
          className="rounded-2xl sm:rounded-3xl px-1 py-2 space-y-1"
          style={{
            backgroundColor: "var(--theme-bg-card)",
            borderColor: "var(--theme-border)",
            border: "1px solid var(--theme-border)",
            boxShadow: "0 2px 12px rgba(0,0,0,0.06)",
          }}
        >
          <div className="px-3 py-2">
            <div className="skeleton-line h-3 w-3/5 rounded" />
          </div>
          <div className="flex items-center justify-between px-2 pb-2">
            <div className="flex items-center gap-2">
              <div className="skeleton-line size-8 rounded-full" />
              <div className="skeleton-line size-8 rounded-full" />
              <div className="skeleton-line size-8 rounded-full" />
              <div className="skeleton-line size-8 rounded-full" />
            </div>
            <div className="skeleton-line size-8 rounded-full" />
          </div>
        </div>
      </div>

      {/* Desktop: Suggestions skeleton */}
      <div className="w-full max-w-[36rem] px-2 mt-5 hidden sm:block">
        {/* Label + refresh */}
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-center gap-1.5">
            <div className="skeleton-line size-3 rounded-full" />
            <SkeletonLine width="w-16" className="!h-3.5" />
          </div>
          <SkeletonLine width="w-20" className="!h-7 !rounded-lg" />
        </div>
        {/* 2x2 suggestion grid */}
        <div className="grid grid-cols-2 gap-2.5">
          {[0, 1, 2, 3].map((i) => (
            <div
              key={i}
              className="flex items-center gap-3 rounded-xl border px-4 py-3"
              style={{
                backgroundColor: "var(--theme-bg-card)",
                borderColor: "var(--theme-border)",
              }}
            >
              <div className="skeleton-line size-7 rounded-lg shrink-0" />
              <SkeletonLine
                width={i % 2 === 0 ? "w-3/4" : "w-4/5"}
                className="!h-[13.5px] flex-1"
              />
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
