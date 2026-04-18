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
        {/* Header skeleton — matches real Header: no border-b, uses padding */}
        <div className="relative z-50 flex items-center px-3 pt-3 sm:px-4 pb-1 shrink-0">
          <div className="flex items-center gap-2 flex-shrink-0">
            <div className="skeleton-line size-8 rounded-lg" />
          </div>
          <div className="flex items-center gap-2 sm:gap-3 ml-2 sm:hidden">
            <div className="skeleton-line h-4 w-24 sm:w-28 rounded-md" />
          </div>
          <div className="flex items-center gap-1.5 sm:gap-2 ml-auto flex-shrink-0">
            <div className="skeleton-line size-8 rounded-lg sm:hidden" />
            <div className="skeleton-line size-8 rounded-lg hidden sm:block" />
            <div className="skeleton-line size-8 rounded-lg hidden sm:block" />
            <div className="skeleton-line size-8 rounded-lg hidden sm:block" />
            <div className="skeleton-line size-8 rounded-lg hidden sm:block" />
            <div className="skeleton-line size-8 rounded-lg hidden sm:block" />
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

/** Skeleton that mimics a chat conversation layout (user + assistant alternating) with input */
export function ChatSkeleton({ count = 3 }: { count?: number }) {
  // Each entry: [bubble width, ...line widths] — mimics natural user queries of varying length
  const userMsgs = [
    { bubble: "w-[75%] sm:w-[55%]", lines: ["100%", "82%"] },
    { bubble: "w-[85%] sm:w-[65%]", lines: ["100%"] },
    { bubble: "w-[50%] sm:w-[35%]", lines: ["100%"] },
  ];

  return (
    <div className="flex flex-col h-full animate-fade-in">
      {/* Message area — fills available space, pushes input to bottom */}
      <div className="flex-1 overflow-hidden">
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

              {/* ── Assistant response ── matches ChatMessage structure ── */}
              <div className="group w-full mb-3 sm:mb-4">
                <div className="mx-auto flex flex-col max-w-3xl xl:max-w-5xl px-4 sm:px-6">
                  <div className="min-w-0 min-h-0">
                    {/* Avatar + Role label */}
                    <div className="mb-3 flex items-center gap-2">
                      <div className="skeleton-line size-7 rounded-full shrink-0" />
                      <SkeletonLine
                        width="w-16"
                        className="!h-4 sm:!h-[18px]"
                      />
                    </div>
                    {/* Response content skeleton — variable line pattern */}
                    <div className="space-y-3 px-2 my-2">
                      <div className="skeleton-line w-full h-2 sm:h-[7px] rounded-full" />
                      <div className="flex gap-2 sm:gap-3">
                        <div className="skeleton-line flex-1 h-2 sm:h-[7px] rounded-full" />
                        <div className="skeleton-line flex-1 h-2 sm:h-[7px] rounded-full" />
                        <div className="skeleton-line w-2/5 h-2 sm:h-[7px] rounded-full hidden sm:block" />
                      </div>
                      <div className="flex gap-2 sm:gap-3">
                        <div className="skeleton-line flex-1 h-2 sm:h-[7px] rounded-full" />
                        <div className="skeleton-line w-1/3 h-2 sm:h-[7px] rounded-full" />
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          );
        })}
      </div>

      {/* ── ChatInput skeleton at bottom ── matches real ChatInput rounded-3xl container */}
      <div className="shrink-0 sm:px-4 pb-3 pt-1">
        <div className="mx-auto max-w-3xl xl:max-w-5xl px-2">
          <div
            className="flex flex-col w-full rounded-3xl px-1 border"
            style={{
              backgroundColor: "var(--theme-bg-card)",
              borderColor: "var(--theme-border)",
              boxShadow: "0 2px 12px rgba(0,0,0,0.06)",
            }}
          >
            {/* Textarea area — matches real min-h-[52px] + pt-2.5 */}
            <div className="px-2.5 py-2 flex items-start gap-2">
              <div className="skeleton-line h-3 w-3/5 rounded flex-1 pt-2.5 min-h-[52px]" />
            </div>
            {/* Bottom toolbar — matches real ChatInput toolbar layout */}
            <div className="flex justify-between pt-3 pb-3 px-2 mx-0.5 max-w-full">
              <div className="flex items-center gap-2 overflow-hidden">
                <div className="skeleton-line size-8 rounded-full shrink-0" />
                <div className="skeleton-line size-8 rounded-full shrink-0 hidden sm:block" />
                <div className="skeleton-line size-8 rounded-full shrink-0 hidden sm:block" />
                <div className="skeleton-line size-8 rounded-full shrink-0" />
              </div>
              <div className="skeleton-line size-8 rounded-full shrink-0" />
            </div>
          </div>
          {/* Keyboard shortcut hint — desktop only, matches real ChatInput */}
          <div className="hidden sm:flex mx-auto mt-3 px-2 max-w-3xl xl:max-w-5xl justify-center">
            <SkeletonLine width="w-40" className="!h-3" />
          </div>
        </div>
      </div>
    </div>
  );
}

/** Messages-only skeleton (for streaming footer, no input box) */
export function ChatSkeletonMessagesOnly({ count = 1 }: { count?: number }) {
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
            {/* User message */}
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

            {/* Assistant response */}
            <div className="group w-full mb-3 sm:mb-4">
              <div className="mx-auto flex flex-col max-w-3xl xl:max-w-5xl px-4 sm:px-6">
                <div className="min-w-0 min-h-0">
                  <div className="mb-3 flex items-center gap-2">
                    <div className="skeleton-line size-7 rounded-full shrink-0" />
                    <SkeletonLine width="w-16" className="!h-4 sm:!h-[18px]" />
                  </div>
                  <div className="space-y-3 px-2 my-2">
                    <div className="skeleton-line w-full h-2 sm:h-[7px] rounded-full" />
                    <div className="flex gap-2 sm:gap-3">
                      <div className="skeleton-line flex-1 h-2 sm:h-[7px] rounded-full" />
                      <div className="skeleton-line flex-1 h-2 sm:h-[7px] rounded-full" />
                      <div className="skeleton-line w-2/5 h-2 sm:h-[7px] rounded-full hidden sm:block" />
                    </div>
                    <div className="flex gap-2 sm:gap-3">
                      <div className="skeleton-line flex-1 h-2 sm:h-[7px] rounded-full" />
                      <div className="skeleton-line w-1/3 h-2 sm:h-[7px] rounded-full" />
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
      <div className="relative flex flex-col items-center mb-4 sm:mb-8 w-full max-w-[90vw]">
        {/* Mobile icon — matches WelcomePage: size-10 rounded-xl */}
        <div className="sm:hidden mb-3">
          <div className="skeleton-line size-10 rounded-xl shadow-md ring-1 ring-stone-200/60 dark:ring-stone-700/40" />
        </div>
        {/* Greeting line — desktop icon inline */}
        <div className="max-w-[90vw] w-full flex items-center justify-center gap-4">
          <div className="skeleton-line size-12 rounded-full hidden sm:block shadow-md ring-1 ring-stone-200/60 dark:ring-stone-700/40" />
          <SkeletonLine
            width="w-48 sm:w-64 lg:w-80"
            className="!h-[1.65rem] sm:!h-8 md:!h-9 !rounded-lg"
          />
        </div>
        {/* Subtitle */}
        <SkeletonLine
          width="w-36 sm:w-48"
          className="!h-3 sm:!h-4 mt-2 sm:mt-3 !rounded-lg"
        />
      </div>

      {/* ChatInput skeleton — matches real ChatInput rounded-3xl container */}
      <div className="w-full max-w-[48rem]">
        <div
          className="flex flex-col w-full rounded-3xl px-1 border"
          style={{
            backgroundColor: "var(--theme-bg-card)",
            borderColor: "var(--theme-border)",
            boxShadow: "0 2px 12px rgba(0,0,0,0.06)",
          }}
        >
          {/* Textarea area */}
          <div className="px-2.5 py-2 flex items-start gap-2">
            <div className="skeleton-line h-3 w-3/5 rounded flex-1 mt-3 min-h-[52px]" />
          </div>
          {/* Bottom toolbar */}
          <div className="flex justify-between pt-3 pb-3 px-2 mx-0.5 max-w-full">
            <div className="flex items-center gap-2 overflow-hidden">
              <div className="skeleton-line size-8 rounded-full shrink-0" />
              <div className="skeleton-line size-8 rounded-full shrink-0 hidden sm:block" />
              <div className="skeleton-line size-8 rounded-full shrink-0 hidden sm:block" />
              <div className="skeleton-line size-8 rounded-full shrink-0" />
            </div>
            <div className="skeleton-line size-8 rounded-full shrink-0" />
          </div>
        </div>
      </div>

      {/* Suggestions skeleton — mobile: 2 cards, desktop: 4 cards */}
      <div className="w-full px-2 sm:mt-5">
        <div className="w-[19rem] sm:max-w-[36rem] sm:w-full mx-auto">
          {/* Label + refresh */}
          <div className="flex items-center justify-between mb-2 sm:mb-3">
            <div className="flex items-center gap-1.5">
              <div className="skeleton-line size-3 rounded-full" />
              <SkeletonLine width="w-16" className="!h-3 sm:!h-3.5" />
            </div>
            <SkeletonLine width="w-20" className="!h-7 !rounded-lg" />
          </div>
          {/* Mobile: 2 cards */}
          <div className="grid grid-cols-1 gap-2 sm:hidden">
            {[0, 1].map((i) => (
              <div
                key={i}
                className="flex items-center gap-2 sm:gap-3 rounded-xl border px-3 py-2 sm:px-4 sm:py-3"
                style={{
                  backgroundColor: "var(--theme-bg-card)",
                  borderColor: "var(--theme-border)",
                }}
              >
                <div className="skeleton-line size-6 rounded-lg shrink-0" />
                <SkeletonLine
                  width={i === 0 ? "w-3/4" : "w-4/5"}
                  className="!h-[12.5px] flex-1"
                />
              </div>
            ))}
          </div>
          {/* Desktop: 2x2 grid */}
          <div className="hidden sm:grid grid-cols-2 gap-2.5">
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
    </div>
  );
}
