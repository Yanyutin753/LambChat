import { SkeletonLine } from "./primitives";
import { PanelHeaderSkeleton } from "./PanelHeaderSkeleton";
import { PANEL_CARD_SKELETON_COUNT } from "./PanelSkeletonHelpers";

/** Channels page: card grid matching SkillBaseCard (.scb) structure */
export function ChannelsGridSkeleton() {
  return (
    <div className="glass-shell flex h-full flex-col min-h-0 animate-fade-in">
      <PanelHeaderSkeleton hasSearch={false} />
      <div className="flex-1 overflow-y-auto py-4">
        <div className="mx-auto max-w-full">
          <div className="grid auto-grid-cols gap-4 p-3 sm:p-4">
            {Array.from({ length: PANEL_CARD_SKELETON_COUNT }).map((_, i) => (
              <div key={i} className="scb">
                {/* Banner */}
                <div
                  className="h-12 w-full shrink-0 relative"
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
                {/* Card body */}
                <div className="flex flex-1 flex-col -mt-3 pt-5 p-4">
                  {/* Icon + name */}
                  <div className="flex items-start gap-3">
                    <div className="scb__icon-ring shrink-0 skeleton-line" />
                    <div className="min-w-0 flex-1">
                      <SkeletonLine
                        width={i % 2 === 0 ? "w-3/4" : "w-1/2"}
                        className="!h-4"
                      />
                    </div>
                  </div>
                  {/* Status pill */}
                  <div className="mt-1.5 sm:mt-2">
                    <SkeletonLine
                      width={
                        i % 3 === 0
                          ? "w-16 sm:w-20"
                          : i % 3 === 1
                            ? "w-12"
                            : "w-8"
                      }
                      className="!h-4 !rounded-full"
                    />
                  </div>
                  {/* Description */}
                  <div className="mt-3 space-y-1.5">
                    <SkeletonLine width="w-full" className="!h-2.5 sm:!h-3" />
                    <SkeletonLine
                      width={i % 2 === 0 ? "w-5/6" : "w-2/3"}
                      className="!h-2.5 sm:!h-3"
                    />
                  </div>
                  {/* Tags row */}
                  <div className="mt-3">
                    <SkeletonLine
                      width="w-20 sm:w-24"
                      className="!h-5 !rounded-lg"
                    />
                  </div>
                  <div className="flex-1" />
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

/** Channels panel: form-based configuration (status card + config form) */
export function ChannelConfigSkeleton() {
  return (
    <div className="glass-shell flex h-full flex-col min-h-0 animate-fade-in">
      <PanelHeaderSkeleton hasSearch={false} />
      <div className="flex-1 overflow-y-auto py-2 sm:py-4 px-4">
        <div className="space-y-4">
          {/* Status card */}
          <div className="glass-card rounded-xl p-4">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-3">
                <SkeletonLine width="w-8" className="!h-3" />
                <SkeletonLine width="w-24 sm:w-32" className="!h-4" />
              </div>
              <SkeletonLine width="w-20 sm:w-24" className="!h-8 !rounded-lg" />
            </div>
          </div>
          {/* Configuration card — form fields */}
          <div className="glass-card rounded-xl p-4">
            <div className="space-y-4">
              {/* Instance name field */}
              <div className="space-y-1.5">
                <SkeletonLine width="w-20" className="!h-3" />
                <div className="skeleton-line h-10 w-full rounded-lg" />
              </div>
              {/* Toggle row */}
              <div className="flex items-center justify-between">
                <SkeletonLine width="w-24" className="!h-3.5" />
                <SkeletonLine width="w-10 h-5" className="!rounded-full" />
              </div>
              {/* Additional fields */}
              {Array.from({ length: 4 }).map((_, i) => (
                <div key={i} className="space-y-1.5">
                  <SkeletonLine
                    width={i % 2 === 0 ? "w-28" : "w-16"}
                    className="!h-3"
                  />
                  <div className="skeleton-line h-10 w-full rounded-lg" />
                </div>
              ))}
              {/* Agent selector */}
              <div className="space-y-1.5">
                <SkeletonLine width="w-16" className="!h-3" />
                <div className="skeleton-line h-10 w-full rounded-lg" />
              </div>
            </div>
          </div>
          {/* Help card */}
          <div className="glass-card-subtle rounded-xl p-4">
            <SkeletonLine width="w-16" className="!h-4 !mb-2" />
            {Array.from({ length: 3 }).map((_, i) => (
              <div key={i} className="flex items-start gap-2 mb-1.5">
                <SkeletonLine
                  width="w-4"
                  className="!h-4 !rounded-full !shrink-0"
                />
                <SkeletonLine
                  width={i === 0 ? "w-3/4" : i === 1 ? "w-2/3" : "w-4/5"}
                  className="!h-3"
                />
              </div>
            ))}
          </div>
        </div>
      </div>
      {/* Footer action buttons */}
      <div className="border-t border-[var(--theme-border)] px-3 py-3 sm:px-4">
        <div className="flex items-center justify-end gap-2">
          <SkeletonLine width="w-16 sm:w-20" className="!h-9 !rounded-lg" />
          <SkeletonLine width="w-20 sm:w-24" className="!h-9 !rounded-lg" />
        </div>
      </div>
    </div>
  );
}
