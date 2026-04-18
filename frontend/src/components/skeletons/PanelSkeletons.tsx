import { SkeletonLine } from "./primitives";
import { PanelHeaderSkeleton } from "./PanelHeaderSkeleton";

/* ═══════════════════════════════════════════════════════
   Panel-specific skeletons
   ═══════════════════════════════════════════════════════ */

/** Skills panel: card grid with tags */
export function SkillsPanelSkeleton() {
  return (
    <div className="flex h-full flex-col gap-4 animate-fade-in">
      <PanelHeaderSkeleton />
      <div className="flex-1 overflow-y-auto min-h-0 p-2 sm:p-4">
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          {Array.from({ length: 6 }).map((_, i) => (
            <div key={i} className="panel-card flex flex-col p-4 sm:p-5">
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

/** Marketplace panel: card grid with gradient banners */
export function MarketplacePanelSkeleton() {
  return (
    <div className="flex h-full flex-col gap-3 sm:gap-4 animate-fade-in">
      <PanelHeaderSkeleton />
      <div className="flex-1 overflow-y-auto min-h-0 p-4 sm:p-6">
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-5">
          {Array.from({ length: 9 }).map((_, i) => (
            <div key={i} className="panel-card overflow-hidden !p-0">
              {/* Gradient banner */}
              <div
                className="h-10 sm:h-12 w-full"
                style={{
                  background: `linear-gradient(135deg, ${
                    [
                      "var(--theme-primary-light)",
                      "color-mix(in srgb, var(--theme-primary-light) 60%, var(--theme-bg))",
                      "var(--theme-bg-card)",
                    ][i % 3]
                  }, var(--theme-bg-card))`,
                }}
              />
              <div className="p-3 sm:p-4">
                <div className="flex items-start gap-2.5 sm:gap-3">
                  {/* Avatar overlapping banner */}
                  <div
                    className="skeleton-line size-8 sm:size-10 rounded-xl shrink-0 -mt-5 sm:-mt-6 ring-2"
                    style={
                      {
                        "--tw-ring-color": "var(--theme-bg-card)",
                      } as React.CSSProperties
                    }
                  />
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
                <div className="mt-2.5 sm:mt-3 flex items-center justify-between">
                  <SkeletonLine
                    width="w-12 sm:w-14"
                    className="!h-4 sm:!h-5 !rounded-full"
                  />
                  <div className="flex items-center gap-1.5">
                    <div className="skeleton-line size-7 rounded-lg" />
                    <div className="skeleton-line size-7 rounded-lg" />
                  </div>
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

/** Users panel: table rows (desktop) + cards (mobile) */
export function UsersPanelSkeleton() {
  return (
    <div className="flex h-full flex-col gap-4 animate-fade-in">
      <PanelHeaderSkeleton />
      <div className="flex-1 overflow-y-auto min-h-0 p-3 sm:p-6">
        {/* Desktop table */}
        <div className="hidden sm:block">
          <div className="panel-card !p-0 overflow-hidden">
            {/* Table header */}
            <div
              className="flex items-center gap-4 px-4 py-3"
              style={{
                backgroundColor:
                  "var(--glass-bg-subtle, color-mix(in srgb, var(--theme-bg) 80%, white))",
              }}
            >
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
                className="flex items-center gap-4 px-4 py-3"
                style={{ borderTop: "1px solid var(--theme-border)" }}
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
        <div className="space-y-2.5 sm:hidden">
          {Array.from({ length: 4 }).map((_, i) => (
            <div key={i} className="panel-card p-3.5">
              <div className="flex items-center gap-3">
                <div className="skeleton-line size-10 rounded-full shrink-0" />
                <div className="flex-1 min-w-0">
                  <SkeletonLine
                    width={i % 2 === 0 ? "w-24" : "w-20"}
                    className="!h-4"
                  />
                  <SkeletonLine width="w-36" className="!h-3 mt-1" />
                </div>
                <div className="skeleton-line size-7 rounded-lg shrink-0" />
              </div>
              <div className="mt-3 flex items-center justify-between">
                <div className="flex gap-1.5">
                  <SkeletonLine width="w-14" className="!h-5 !rounded-full" />
                  <SkeletonLine width="w-16" className="!h-5 !rounded-full" />
                </div>
                <SkeletonLine width="w-16" className="!h-5 !rounded-full" />
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

/** Roles panel: vertically stacked cards matching real RolesPanel layout */
export function RolesPanelSkeleton() {
  return (
    <div className="flex h-full flex-col gap-3 sm:gap-4 animate-fade-in">
      <PanelHeaderSkeleton />
      <div className="flex-1 overflow-y-auto p-3 sm:p-6">
        <div className="grid gap-4">
          {Array.from({ length: 4 }).map((_, i) => (
            <div key={i} className="panel-card !p-4">
              <div className="flex items-start justify-between gap-2">
                <div className="flex-1 min-w-0">
                  {/* Icon + name row */}
                  <div className="flex items-center gap-2">
                    <div
                      className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg"
                      style={{
                        backgroundColor:
                          "var(--glass-bg-subtle, color-mix(in srgb, var(--theme-bg) 80%, white))",
                      }}
                    >
                      <div className="skeleton-line size-[14px] rounded-sm" />
                    </div>
                    <div>
                      <SkeletonLine
                        width={i % 2 === 0 ? "w-20 sm:w-28" : "w-28 sm:w-36"}
                        className="!h-[15px] sm:!h-[16px]"
                      />
                      {i === 0 && (
                        <SkeletonLine
                          width="w-16 sm:w-20"
                          className="!h-4 sm:!h-5 !rounded-md ml-2"
                        />
                      )}
                    </div>
                  </div>
                  <SkeletonLine
                    width="w-3/4"
                    className="!h-2.5 sm:!h-3 mt-1.5 sm:mt-2"
                  />
                  <SkeletonLine
                    width="w-1/2"
                    className="!h-2.5 sm:!h-3 mt-0.5 !opacity-60"
                  />
                  {/* Permission tags */}
                  <div className="mt-2.5 sm:mt-3 flex flex-wrap gap-1 sm:gap-1.5">
                    <SkeletonLine
                      width="w-14 sm:w-16"
                      className="!h-4 sm:!h-5 !rounded-lg"
                    />
                    <SkeletonLine
                      width="w-16 sm:w-20"
                      className="!h-4 sm:!h-5 !rounded-lg"
                    />
                    <SkeletonLine
                      width="w-12 sm:w-14"
                      className="!h-4 sm:!h-5 !rounded-lg"
                    />
                  </div>
                </div>
                {/* Action buttons */}
                <div className="flex items-center gap-1.5 sm:gap-2 shrink-0">
                  <div className="skeleton-line size-7 sm:size-8 rounded-lg" />
                  <div className="skeleton-line size-7 sm:size-8 rounded-lg" />
                  <div className="skeleton-line size-7 sm:size-8 rounded-lg" />
                </div>
              </div>
              {/* Timestamp row */}
              <div className="mt-3 flex items-center gap-4">
                <SkeletonLine
                  width="w-24 sm:w-28"
                  className="!h-2.5 !opacity-50"
                />
                <SkeletonLine
                  width="w-24 sm:w-28"
                  className="!h-2.5 !opacity-50"
                />
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

/** MCP panel: server cards matching real MCPServerCard structure */
export function MCPPanelSkeleton() {
  return (
    <div className="flex h-full flex-col gap-3 sm:gap-4 animate-fade-in">
      <PanelHeaderSkeleton />
      <div className="flex-1 overflow-y-auto p-3 sm:p-4 space-y-3">
        {Array.from({ length: 4 }).map((_, i) => (
          <div key={i} className="panel-card !p-4">
            <div className="flex items-start justify-between gap-2">
              <div className="flex-1 min-w-0">
                {/* Server name + status badges */}
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
                {/* URL row */}
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
              {/* Action buttons */}
              <div className="flex items-center gap-1 sm:gap-1.5 shrink-0">
                <div className="skeleton-line size-7 sm:size-8 rounded-full" />
                <div className="skeleton-line size-7 sm:size-8 rounded-lg" />
                <div className="skeleton-line size-7 sm:size-8 rounded-lg hidden sm:block" />
                <div className="skeleton-line size-7 sm:size-8 rounded-lg hidden sm:block" />
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

/** Feedback panel: stats cards + feedback items */
export function FeedbackPanelSkeleton() {
  return (
    <div className="flex h-full flex-col gap-3 sm:gap-4 animate-fade-in">
      <PanelHeaderSkeleton hasSearch={false} />
      <div className="flex-1 overflow-y-auto min-h-0 p-4 sm:p-6">
        {/* Stats grid — matches glass-card style */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 sm:gap-4 mb-4">
          {[0, 1, 2, 3].map((i) => (
            <div key={i} className="glass-card rounded-xl p-4">
              <div className="flex items-center gap-2 sm:gap-3">
                <div
                  className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg"
                  style={{
                    backgroundColor:
                      "var(--glass-bg-subtle, color-mix(in srgb, var(--theme-bg) 80%, white))",
                  }}
                >
                  <div className="skeleton-line size-6 rounded-md" />
                </div>
                <div className="min-w-0">
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
        {/* Feedback list */}
        <div className="space-y-3">
          {Array.from({ length: 5 }).map((_, i) => (
            <div key={i} className="panel-card !p-4 sm:!p-5">
              <div className="flex items-center justify-between gap-2">
                <div className="flex items-center gap-2 sm:gap-3 min-w-0">
                  <div className="skeleton-line size-9 sm:size-10 rounded-full shrink-0" />
                  <div className="min-w-0">
                    <SkeletonLine
                      width={i % 2 === 0 ? "w-16 sm:w-20" : "w-20 sm:w-24"}
                      className="!h-3.5 sm:!h-4"
                    />
                    <SkeletonLine
                      width="w-32 sm:w-40"
                      className="!h-2.5 !mt-1 !opacity-50"
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

/** Channels panel: channel type cards */
export function ChannelsPanelSkeleton() {
  return (
    <div className="flex h-full flex-col gap-3 sm:gap-4 animate-fade-in">
      <PanelHeaderSkeleton hasSearch={false} />
      <div className="flex-1 overflow-y-auto p-3 sm:p-4 space-y-4">
        {Array.from({ length: 4 }).map((_, i) => (
          <div key={i} className="panel-card !p-4">
            <div className="flex items-center gap-2.5 sm:gap-3">
              <div
                className="flex size-8 sm:size-10 shrink-0 items-center justify-center rounded-xl"
                style={{
                  backgroundColor:
                    "var(--glass-bg-subtle, color-mix(in srgb, var(--theme-bg) 80%, white))",
                }}
              >
                <div className="skeleton-line size-[18px] sm:size-5 rounded-md" />
              </div>
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

/** Agent panel: agent list cards with tab switcher */
export function AgentPanelSkeleton() {
  return (
    <div className="flex h-full flex-col gap-3 sm:gap-4 animate-fade-in">
      <PanelHeaderSkeleton hasSearch={false} />
      {/* Tab switcher */}
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
      <div className="flex-1 overflow-y-auto px-4 py-5 sm:px-6 space-y-5">
        {Array.from({ length: 5 }).map((_, i) => (
          <div key={i} className="panel-card flex items-center gap-3.5 !p-4">
            <div
              className="flex size-11 shrink-0 items-center justify-center rounded-xl"
              style={{
                backgroundColor:
                  "var(--glass-bg-subtle, color-mix(in srgb, var(--theme-bg) 80%, white))",
              }}
            >
              <div className="skeleton-line size-[18px] sm:size-5 rounded-md" />
            </div>
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

/** Model panel: model config rows with tab switcher */
export function ModelPanelSkeleton() {
  return (
    <div className="flex h-full flex-col gap-3 sm:gap-4 animate-fade-in">
      <PanelHeaderSkeleton hasSearch={false} />
      {/* Tab switcher */}
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
      <div className="flex-1 overflow-y-auto px-3 py-4 sm:px-6 sm:py-5 space-y-1">
        {Array.from({ length: 6 }).map((_, i) => (
          <div key={i} className="panel-card !p-0">
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
