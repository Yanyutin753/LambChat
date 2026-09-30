import { SkeletonLine } from "./primitives";
import { PanelHeaderSkeleton } from "./PanelHeaderSkeleton";
import {
  PANEL_CARD_SKELETON_COUNT,
  PANEL_ROW_SKELETON_COUNT,
  PanelPaginationSkeleton,
} from "./PanelSkeletonHelpers";

export function BookmarksListSkeleton() {
  return (
    <div className="grid auto-grid-cols gap-3" aria-hidden="true">
      {Array.from({ length: PANEL_CARD_SKELETON_COUNT }).map((_, i) => (
        <div key={i} className="glass-card flex flex-col rounded-xl p-4 sm:p-5">
          <div className="flex items-start justify-between gap-2">
            <SkeletonLine width="w-2/3" className="!h-4" />
            <div className="skeleton-line size-7 shrink-0 rounded-md" />
          </div>
          <div className="mt-3 flex flex-wrap gap-1.5">
            <SkeletonLine width="w-28" className="!h-5" />
            <SkeletonLine width="w-20" className="!h-5" />
          </div>
        </div>
      ))}
    </div>
  );
}

export function BookmarksPanelSkeleton() {
  return (
    <div className="flex h-full min-h-0 flex-col">
      <PanelHeaderSkeleton hasSearch={false} hasSubtitle />
      <div className="panel-body flex-1 min-h-0 overflow-y-auto">
        <BookmarksListSkeleton />
      </div>
      <PanelPaginationSkeleton />
    </div>
  );
}

export function NotificationsListSkeleton() {
  return (
    <div className="space-y-3" aria-hidden="true">
      {Array.from({ length: PANEL_ROW_SKELETON_COUNT }).map((_, i) => (
        <div
          key={i}
          className="glass-card overflow-hidden rounded-xl p-4 sm:p-5"
        >
          <div className="flex items-center gap-2 sm:gap-3">
            <SkeletonLine width="w-12" className="!h-4" />
            <SkeletonLine width="w-1/2" className="!h-4" />
            <SkeletonLine width="w-14" className="!h-5 ml-auto" />
          </div>
          <SkeletonLine width="w-40" className="!h-3 mt-3 !opacity-60" />
          <SkeletonLine width="w-3/4" className="!h-3 mt-3" />
        </div>
      ))}
    </div>
  );
}

export function NotificationsPanelSkeleton() {
  return (
    <div className="glass-shell flex h-full min-h-0 flex-col">
      <PanelHeaderSkeleton hasSearch={false} hasSubtitle />
      <div className="panel-body flex-1 min-h-0 overflow-y-auto">
        <NotificationsListSkeleton />
      </div>
      <PanelPaginationSkeleton />
    </div>
  );
}

export function TeamListSkeleton() {
  return (
    <div className="grid auto-grid-cols gap-3" aria-hidden="true">
      {Array.from({ length: PANEL_CARD_SKELETON_COUNT }).map((_, i) => (
        <div
          key={i}
          className="team-card scb flex h-full flex-col overflow-hidden border border-[var(--theme-border)] bg-[var(--theme-bg-card)]"
        >
          <div className="scb__banner skeleton-line h-12 shrink-0" />
          <div className="flex flex-1 flex-col p-4 pt-5">
            <div className="flex items-start gap-3">
              <div className="team-card__identity-avatar skeleton-line shrink-0" />
              <div className="min-w-0 flex-1">
                <SkeletonLine width="w-3/4" className="!h-4" />
                <SkeletonLine width="w-1/2" className="!h-3 mt-1.5" />
              </div>
            </div>
            <div className="mt-3 min-h-[3.25em] space-y-2">
              <SkeletonLine />
              <SkeletonLine width="w-2/3" />
            </div>
            <div className="team-card__avatars mt-3">
              {[0, 1, 2].map((member) => (
                <div
                  key={member}
                  className="skeleton-line size-6 rounded-full"
                />
              ))}
            </div>
            <div className="mt-3 flex gap-1.5">
              <SkeletonLine width="w-16" className="!h-5" />
              <SkeletonLine width="w-20" className="!h-5" />
            </div>
            <div className="scb__footer flex items-center justify-between gap-2">
              <SkeletonLine width="w-16" />
              <div className="skeleton-line h-7 w-24 rounded-lg" />
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}

export function TeamPanelSkeleton() {
  return (
    <div className="skill-theme-shell flex h-full min-h-0 flex-col">
      <PanelHeaderSkeleton hasSubtitle hasSearchAccessory hasSearchActions />
      <div className="panel-body skill-content-area flex-1 min-h-0 overflow-y-auto">
        <TeamListSkeleton />
      </div>
      <PanelPaginationSkeleton />
    </div>
  );
}
