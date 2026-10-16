import { SkeletonLine } from "./primitives";
import { PanelHeaderSkeleton } from "./PanelHeaderSkeleton";
import {
  PANEL_CARD_SKELETON_COUNT,
  PANEL_ROW_SKELETON_COUNT,
} from "./PanelSkeletonHelpers";

/** Full route fallback, or cards inside the page's existing header/body. */
export function ChannelsGridSkeleton({
  contentOnly = false,
}: { contentOnly?: boolean } = {}) {
  const cards = (
    <div className="grid auto-grid-cols gap-4" aria-hidden="true">
      {Array.from({ length: PANEL_CARD_SKELETON_COUNT }).map((_, i) => (
        <div
          key={i}
          className="scb flex h-full flex-col overflow-hidden rounded-2xl bg-theme-bg-card"
        >
          <div className="scb__banner skeleton-line h-12 w-full shrink-0 relative" />
          <div className="scb__body flex flex-1 flex-col p-3 -mt-3 pt-4">
            <div className="scb__header flex items-center gap-2">
              <div className="flex size-9 shrink-0 items-center justify-center">
                <SkeletonLine width="w-6" className="!h-6" />
              </div>
              <div className="min-w-0 flex-1">
                <div className="flex h-[1.4em] items-center text-16">
                  <SkeletonLine
                    width={i % 2 === 0 ? "w-3/4" : "w-1/2"}
                    className="!h-4"
                  />
                </div>
                <div className="scb__status">
                  <SkeletonLine
                    width="w-16"
                    className="!h-[calc(1.25em+4px)] !rounded-full"
                  />
                </div>
              </div>
            </div>
            <div className="scb__description flex h-[1.625em] items-center text-13">
              <SkeletonLine
                width={i % 2 === 0 ? "w-5/6" : "w-2/3"}
                className="!h-3"
              />
            </div>
            <div className="w-24 rounded-lg border border-transparent py-1 text-12">
              <SkeletonLine className="!h-[1.6em] !rounded-lg" />
            </div>
          </div>
        </div>
      ))}
    </div>
  );
  if (contentOnly) return cards;
  return (
    <div className="flex h-full min-h-0 flex-col">
      <PanelHeaderSkeleton hasSearch={false} hasSubtitle hasActions={false} />
      <div className="panel-body flex-1 overflow-y-auto">{cards}</div>
    </div>
  );
}

/** Instance rows match the loaded name, status/date row and trailing arrow. */
export function ChannelInstancesSkeleton() {
  return (
    <div className="panel-stack mx-auto max-w-full" aria-hidden="true">
      {Array.from({ length: PANEL_ROW_SKELETON_COUNT }).map((_, i) => (
        <div key={i} className="panel-card flex items-center gap-3">
          <div className="min-w-0 flex-1">
            <div className="flex h-[1.6em] items-center">
              <SkeletonLine width="w-48" className="!h-4" />
            </div>
            <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-2">
              <SkeletonLine
                width="w-16"
                className="!h-[calc(1.6em+4px)] !rounded-full text-12"
              />
              <SkeletonLine width="w-36" className="!h-3" />
            </div>
          </div>
          <SkeletonLine width="w-[18px]" className="!h-[18px] shrink-0" />
        </div>
      ))}
    </div>
  );
}

/** Channels panel: form-based configuration (status card + config form) */
export function ChannelConfigSkeleton() {
  return (
    <div className="glass-shell flex h-full flex-col min-h-0">
      <PanelHeaderSkeleton hasSearch={false} hasSubtitle />
      <div className="panel-body flex-1 min-h-0 overflow-y-auto">
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
