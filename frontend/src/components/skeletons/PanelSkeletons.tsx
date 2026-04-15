import { SkeletonLine } from "./primitives";
import { PanelHeaderSkeleton } from "./PanelHeaderSkeleton";

/* ═══════════════════════════════════════════════════════
   Panel-specific skeletons
   ═══════════════════════════════════════════════════════ */

/** Skills panel: 2-col card grid */
export function SkillsPanelSkeleton() {
  return (
    <div className="flex h-full flex-col gap-4 animate-fade-in">
      <PanelHeaderSkeleton />
      <div className="flex-1 overflow-y-auto min-h-0">
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          {Array.from({ length: 6 }).map((_, i) => (
            <div key={i} className="panel-card flex flex-col p-3 sm:p-5">
              <div className="flex items-start justify-between gap-2 sm:gap-3">
                <div className="flex-1 min-w-0">
                  <SkeletonLine
                    width={i % 2 === 0 ? "w-3/4" : "w-1/2"}
                    className="!h-[16px] sm:!h-[18px]"
                  />
                  <SkeletonLine
                    width="w-16 sm:w-20"
                    className="!h-4 sm:!h-5 mt-1.5 sm:mt-2 !rounded-full"
                  />
                </div>
              </div>
              <div className="mt-2 space-y-1.5">
                <SkeletonLine width="w-full" className="!h-2.5 sm:!h-3" />
                <SkeletonLine
                  width={i % 2 === 0 ? "w-5/6" : "w-2/3"}
                  className="!h-2.5 sm:!h-3"
                />
              </div>
              <div className="mt-3 sm:mt-4 flex flex-wrap gap-1.5 sm:gap-2">
                <SkeletonLine
                  width="w-14 sm:w-16"
                  className="!h-4 sm:!h-5 !rounded-full"
                />
                <SkeletonLine
                  width="w-20 sm:w-24"
                  className="!h-4 sm:!h-5 !rounded-full"
                />
              </div>
              <div className="mt-2.5 sm:mt-3 flex flex-wrap gap-1.5 sm:gap-2">
                <SkeletonLine
                  width="w-12 sm:w-14"
                  className="!h-4 sm:!h-5 !rounded-full"
                />
                <SkeletonLine
                  width="w-14 sm:w-18"
                  className="!h-4 sm:!h-5 !rounded-full"
                />
                <SkeletonLine
                  width="w-10 sm:w-12"
                  className="!h-4 sm:!h-5 !rounded-full"
                />
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

/** Marketplace panel: 3-col card grid with gradient banners */
export function MarketplacePanelSkeleton() {
  return (
    <div className="flex h-full flex-col gap-3 sm:gap-4 animate-fade-in">
      <PanelHeaderSkeleton />
      <div className="flex-1 overflow-y-auto min-h-0">
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3 sm:gap-4">
          {Array.from({ length: 9 }).map((_, i) => (
            <div key={i} className="panel-card overflow-hidden">
              <div className="skeleton-line h-10 sm:h-12 w-full !rounded-none" />
              <div className="p-3 sm:p-4">
                <div className="flex items-start gap-2.5 sm:gap-3">
                  <div className="skeleton-line size-8 sm:size-10 rounded-xl shrink-0 -mt-5 sm:-mt-6 ring-2" />
                  <div className="flex-1 min-w-0">
                    <SkeletonLine
                      width={i % 3 === 0 ? "w-3/4" : "w-1/2"}
                      className="!h-[15px] sm:!h-[16px]"
                    />
                    <SkeletonLine
                      width="w-16 sm:w-20"
                      className="!h-2.5 sm:!h-3 mt-1"
                    />
                  </div>
                </div>
                <div className="mt-2 space-y-1">
                  <SkeletonLine width="w-full" className="!h-2.5 sm:!h-3" />
                  <SkeletonLine width="w-4/5" className="!h-2.5 sm:!h-3" />
                </div>
                <div className="mt-2.5 sm:mt-3">
                  <SkeletonLine
                    width="w-12 sm:w-14"
                    className="!h-4 sm:!h-5 !rounded-full"
                  />
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

/** Users panel: table rows */
export function UsersPanelSkeleton() {
  return (
    <div className="flex h-full flex-col gap-4 animate-fade-in">
      <PanelHeaderSkeleton />
      <div className="flex-1 overflow-y-auto min-h-0">
        {/* Desktop table */}
        <div className="hidden sm:block">
          <div
            className="rounded-xl border overflow-hidden"
            style={{ borderColor: "var(--theme-border)" }}
          >
            <div className="flex items-center gap-4 px-4 py-3 bg-stone-50 dark:bg-stone-800/40">
              <SkeletonLine width="w-24" className="!h-3 !rounded" />
              <SkeletonLine width="w-32" className="!h-3 !rounded flex-1" />
              <SkeletonLine width="w-20" className="!h-3 !rounded" />
              <SkeletonLine width="w-16" className="!h-3 !rounded" />
              <SkeletonLine width="w-20" className="!h-3 !rounded" />
              <SkeletonLine width="w-16" className="!h-3 !rounded" />
            </div>
            {Array.from({ length: 6 }).map((_, i) => (
              <div
                key={i}
                className="flex items-center gap-4 px-4 py-3 border-t"
                style={{ borderColor: "var(--theme-border)" }}
              >
                <div className="flex items-center gap-3 w-28 shrink-0">
                  <div className="skeleton-line size-8 rounded-full shrink-0" />
                  <SkeletonLine
                    width={i % 2 === 0 ? "w-16" : "w-20"}
                    className="!h-4"
                  />
                </div>
                <SkeletonLine
                  width={i % 3 === 0 ? "w-36" : "w-44"}
                  className="!h-3.5 flex-1"
                />
                <div className="flex gap-1 w-20 shrink-0">
                  <SkeletonLine width="w-14" className="!h-5 !rounded-full" />
                </div>
                <SkeletonLine
                  width="w-16"
                  className="!h-5 !rounded-full shrink-0"
                />
                <SkeletonLine width="w-20" className="!h-3 shrink-0" />
                <div className="flex gap-1 w-16 shrink-0">
                  <div className="skeleton-line size-7 rounded-lg" />
                  <div className="skeleton-line size-7 rounded-lg" />
                </div>
              </div>
            ))}
          </div>
        </div>
        {/* Mobile cards */}
        <div className="space-y-3 sm:hidden">
          {Array.from({ length: 4 }).map((_, i) => (
            <div key={i} className="panel-card p-4">
              <div className="flex items-center gap-3">
                <div className="skeleton-line size-10 rounded-full shrink-0" />
                <div className="flex-1 min-w-0">
                  <SkeletonLine
                    width={i % 2 === 0 ? "w-24" : "w-20"}
                    className="!h-4"
                  />
                  <SkeletonLine width="w-36" className="!h-3 mt-1" />
                </div>
              </div>
              <div className="mt-3 flex gap-1">
                <SkeletonLine width="w-14" className="!h-5 !rounded-full" />
                <SkeletonLine width="w-16" className="!h-5 !rounded-full" />
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

/** Roles panel: vertically stacked cards */
export function RolesPanelSkeleton() {
  return (
    <div className="flex h-full flex-col gap-3 sm:gap-4 animate-fade-in">
      <PanelHeaderSkeleton />
      <div className="flex-1 overflow-y-auto min-h-0 space-y-3 sm:space-y-4">
        {Array.from({ length: 4 }).map((_, i) => (
          <div key={i} className="panel-card p-3 sm:p-4">
            <div className="flex items-start justify-between gap-2">
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2">
                  <div className="skeleton-line size-7 sm:size-8 rounded-lg shrink-0" />
                  <SkeletonLine
                    width={i % 2 === 0 ? "w-20 sm:w-28" : "w-28 sm:w-36"}
                    className="!h-[15px] sm:!h-[16px]"
                  />
                  {i === 0 && (
                    <SkeletonLine
                      width="w-16 sm:w-20"
                      className="!h-4 sm:!h-5 !rounded-md"
                    />
                  )}
                </div>
                <SkeletonLine
                  width="w-3/4"
                  className="!h-2.5 sm:!h-3 mt-1.5 sm:mt-2"
                />
                <div className="mt-2.5 sm:mt-3 flex flex-wrap gap-1 sm:gap-1.5">
                  <SkeletonLine
                    width="w-14 sm:w-16"
                    className="!h-4 sm:!h-5 !rounded-full"
                  />
                  <SkeletonLine
                    width="w-16 sm:w-20"
                    className="!h-4 sm:!h-5 !rounded-full"
                  />
                  <SkeletonLine
                    width="w-12 sm:w-14"
                    className="!h-4 sm:!h-5 !rounded-full"
                  />
                </div>
              </div>
              <div className="flex gap-1 sm:gap-1.5 shrink-0">
                <div className="skeleton-line size-7 sm:size-8 rounded-lg" />
                <div className="skeleton-line size-7 sm:size-8 rounded-lg" />
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

/** MCP panel: server cards */
export function MCPPanelSkeleton() {
  return (
    <div className="flex h-full flex-col gap-3 sm:gap-4 animate-fade-in">
      <PanelHeaderSkeleton />
      <div className="flex-1 overflow-y-auto min-h-0 space-y-2.5 sm:space-y-3">
        {Array.from({ length: 4 }).map((_, i) => (
          <div key={i} className="panel-card p-3 sm:p-4">
            <div className="flex items-start justify-between gap-2">
              <div className="flex-1 min-w-0">
                <div className="flex flex-wrap items-center gap-1.5 sm:gap-2">
                  <div className="skeleton-line size-4 sm:size-5 rounded shrink-0" />
                  <SkeletonLine
                    width={i % 2 === 0 ? "w-24 sm:w-36" : "w-20 sm:w-28"}
                    className="!h-[15px] sm:!h-[16px]"
                  />
                  <SkeletonLine
                    width="w-10 sm:w-12"
                    className="!h-4 sm:!h-5 !rounded-full"
                  />
                  <SkeletonLine
                    width="w-8 sm:w-10"
                    className="!h-4 sm:!h-5 !rounded-full"
                  />
                </div>
                <div className="mt-1.5 sm:mt-2">
                  <SkeletonLine
                    width="w-3/5"
                    className="!h-4 sm:!h-5 !rounded-md"
                  />
                </div>
                <SkeletonLine
                  width="w-20 sm:w-24"
                  className="!h-2.5 sm:!h-3 mt-1.5 sm:mt-2"
                />
              </div>
              <div className="flex items-center gap-1 sm:gap-1.5 shrink-0">
                <div className="skeleton-line size-7 sm:size-8 rounded-full" />
                <div className="skeleton-line size-7 sm:size-8 rounded-lg" />
                <div className="skeleton-line size-7 sm:size-8 rounded-lg hidden sm:block" />
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

/** Feedback panel: stats + feedback cards */
export function FeedbackPanelSkeleton() {
  return (
    <div className="flex h-full flex-col gap-3 sm:gap-4 animate-fade-in">
      <PanelHeaderSkeleton hasSearch={false} />
      <div className="flex-1 overflow-y-auto min-h-0">
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 sm:gap-3 mb-4">
          {[0, 1, 2, 3].map((i) => (
            <div key={i} className="panel-card p-3 sm:p-4">
              <div className="flex items-center gap-2 sm:gap-3">
                <div className="skeleton-line size-8 sm:size-10 rounded-lg shrink-0" />
                <div>
                  <SkeletonLine
                    width="w-10 sm:w-12"
                    className="!h-2.5 sm:!h-3"
                  />
                  <SkeletonLine
                    width="w-6 sm:w-8"
                    className="!h-5 sm:!h-6 mt-1"
                  />
                </div>
              </div>
            </div>
          ))}
        </div>
        <div className="space-y-2.5 sm:space-y-3">
          {Array.from({ length: 5 }).map((_, i) => (
            <div key={i} className="panel-card p-3 sm:p-5">
              <div className="flex items-center justify-between gap-2">
                <div className="flex items-center gap-2 sm:gap-3 min-w-0">
                  <div className="skeleton-line size-7 sm:size-8 rounded-full shrink-0" />
                  <div className="min-w-0">
                    <SkeletonLine
                      width={i % 2 === 0 ? "w-16 sm:w-20" : "w-20 sm:w-24"}
                      className="!h-3.5 sm:!h-4"
                    />
                  </div>
                </div>
                <SkeletonLine
                  width="w-12 sm:w-16"
                  className="!h-5 sm:!h-6 !rounded-full shrink-0"
                />
              </div>
              <SkeletonLine
                width="w-3/4"
                className="!h-2.5 sm:!h-3 mt-2.5 sm:mt-3"
              />
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

/** Channels page: channel type cards */
export function ChannelsPanelSkeleton() {
  return (
    <div className="flex h-full flex-col gap-3 sm:gap-4 animate-fade-in">
      <PanelHeaderSkeleton hasSearch={false} />
      <div className="flex-1 overflow-y-auto min-h-0 space-y-2.5 sm:space-y-3">
        {Array.from({ length: 4 }).map((_, i) => (
          <div key={i} className="panel-card p-3 sm:p-4">
            <div className="flex items-center gap-2.5 sm:gap-3">
              <div className="skeleton-line size-8 sm:size-10 rounded-xl shrink-0" />
              <div className="flex-1 min-w-0">
                <SkeletonLine
                  width={i % 2 === 0 ? "w-24 sm:w-32" : "w-20 sm:w-28"}
                  className="!h-[15px] sm:!h-[16px]"
                />
                <SkeletonLine width="w-3/5" className="!h-2.5 sm:!h-3 mt-1" />
              </div>
              <SkeletonLine
                width="w-6 sm:w-8"
                className="!h-4 sm:!h-5 !rounded-full shrink-0"
              />
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

/** Agent panel: agent cards */
export function AgentPanelSkeleton() {
  return (
    <div className="flex h-full flex-col gap-3 sm:gap-4 animate-fade-in">
      <PanelHeaderSkeleton hasSearch={false} />
      <div
        className="flex gap-1 p-1 rounded-lg border w-fit"
        style={{ borderColor: "var(--theme-border)" }}
      >
        <SkeletonLine
          width="w-16 sm:w-20"
          className="!h-7 sm:!h-8 !rounded-md"
        />
        <SkeletonLine
          width="w-12 sm:w-16"
          className="!h-7 sm:!h-8 !rounded-md"
        />
      </div>
      <div className="flex-1 overflow-y-auto min-h-0 space-y-2.5 sm:space-y-3">
        {Array.from({ length: 5 }).map((_, i) => (
          <div
            key={i}
            className="flex items-center gap-2.5 sm:gap-3.5 panel-card p-3 sm:p-4"
          >
            <div className="skeleton-line size-9 sm:size-11 rounded-xl shrink-0" />
            <div className="flex-1 min-w-0">
              <SkeletonLine
                width={i % 2 === 0 ? "w-20 sm:w-28" : "w-28 sm:w-36"}
                className="!h-[13px] sm:!h-[14px]"
              />
              <SkeletonLine width="w-3/5" className="!h-2.5 sm:!h-3 mt-1" />
            </div>
            <div className="skeleton-line w-8 sm:w-10 h-4 sm:h-5 rounded-full shrink-0" />
          </div>
        ))}
      </div>
    </div>
  );
}

/** Model panel: model config rows */
export function ModelPanelSkeleton() {
  return (
    <div className="flex h-full flex-col gap-3 sm:gap-4 animate-fade-in">
      <PanelHeaderSkeleton hasSearch={false} />
      <div
        className="flex gap-1 p-1 rounded-lg border w-fit"
        style={{ borderColor: "var(--theme-border)" }}
      >
        <SkeletonLine
          width="w-14 sm:w-16"
          className="!h-7 sm:!h-8 !rounded-md"
        />
        <SkeletonLine
          width="w-20 sm:w-28"
          className="!h-7 sm:!h-8 !rounded-md"
        />
      </div>
      <div className="flex-1 overflow-y-auto min-h-0 space-y-2.5 sm:space-y-3">
        {Array.from({ length: 6 }).map((_, i) => (
          <div key={i} className="panel-card">
            <div className="flex items-center justify-between p-3 sm:p-4 gap-2">
              <div className="flex items-center gap-2 sm:gap-3 flex-1 min-w-0">
                <div className="skeleton-line size-4 sm:size-5 rounded shrink-0" />
                <div className="skeleton-line size-5 sm:size-6 rounded shrink-0" />
                <div className="flex-1 min-w-0">
                  <SkeletonLine
                    width={i % 2 === 0 ? "w-24 sm:w-32" : "w-20 sm:w-28"}
                    className="!h-[13px] sm:!h-[14px]"
                  />
                </div>
              </div>
              <div className="flex items-center gap-1 sm:gap-1.5 shrink-0">
                <div className="skeleton-line w-8 sm:w-10 h-4 sm:h-5 rounded-full" />
                <div className="skeleton-line size-7 sm:size-8 rounded-lg" />
                <div className="skeleton-line size-7 sm:size-8 rounded-lg hidden sm:block" />
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
