import type { ReactNode } from "react";

import { SIDEBAR_COLLAPSED_STORAGE_KEY } from "../../hooks/useAuth";
import { PANEL_ROW_SKELETON_COUNT } from "./PanelSkeletonHelpers";

/** Sidebar skeleton — matches real SessionSidebar layout */
export function SidebarSkeleton() {
  const collapsed = (() => {
    const saved = localStorage.getItem(SIDEBAR_COLLAPSED_STORAGE_KEY);
    return saved !== null ? saved === "true" : false;
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
      <nav
        className="absolute inset-0 flex h-full w-full flex-col items-start select-none"
        style={{
          backgroundColor: "var(--theme-bg-sidebar)",
          borderRight: "1px solid var(--theme-border)",
        }}
      >
        {/* Expand button area */}
        <div className="flex items-center justify-center w-full pt-3">
          <SidebarRailIconSkeleton />
        </div>

        {/* Action icons — matches real rail: NewChat, Search, ScheduledTasks, FileLibrary, RecentChats, More */}
        <div
          className="mt-3 flex-1 min-h-0 overflow-y-auto overflow-x-hidden flex flex-col items-center w-full space-y-1"
          style={{ scrollbarWidth: "none", msOverflowStyle: "none" }}
        >
          {Array.from({ length: 6 }).map((_, i) => (
            <SidebarRailIconSkeleton key={i} />
          ))}
        </div>

        {/* Profile avatar */}
        <div
          className="shrink-0 py-4 w-full flex flex-col items-center border-t"
          style={{ borderColor: "var(--theme-border)" }}
        >
          <div className="skeleton-line size-8 rounded-full" />
        </div>
      </nav>
    </div>
  );
}

/** Skeleton for the expanded sidebar */
function SidebarExpandedSkeleton() {
  return (
    <div className="hidden sm:flex w-64 shrink-0 flex-col overflow-hidden bg-[var(--theme-bg-sidebar)] border-r border-stone-300/70 dark:border-stone-800/60">
      {/* Header area — app icon (h-7) + name + collapse button */}
      <div className="flex items-center justify-between px-3 pt-3 pb-2">
        <div className="flex h-7 items-center gap-1.5">
          <div className="skeleton-line h-7 rounded-full shrink-0" />
          <div className="skeleton-line h-7 w-20 rounded-md" />
        </div>
        <div className="skeleton-line size-8 rounded-lg shrink-0" />
      </div>

      {/* Action buttons — NewChat, Search, ScheduledTasks, FileLibrary, More */}
      <div className="flex flex-col gap-px px-2 mb-2 space-y-1">
        {/* New Chat */}
        <SidebarNavRowSkeleton labelWidth="w-16" />
        {/* Search */}
        <SidebarNavRowSkeleton
          labelWidth="w-14 flex-1"
          trailing={<div className="skeleton-line h-4 w-10 rounded-md" />}
        />
        {/* Scheduled Tasks (permission-gated) */}
        <SidebarNavRowSkeleton labelWidth="w-20" />
        {/* File Library */}
        <SidebarNavRowSkeleton labelWidth="w-16" />
        {/* More (conditional) */}
        <SidebarNavRowSkeleton labelWidth="w-10" />
      </div>

      {/* Session list */}
      <div className="flex-1 overflow-y-auto px-2 [scrollbar-width:none] [&::-webkit-scrollbar]:hidden">
        <div className="flex flex-col gap-px">
          {/* Section header — Projects */}
          <div className="flex items-center justify-between px-[9px] h-9">
            <div className="skeleton-line h-3 w-16 rounded-md" />
            <div className="skeleton-line size-3.5 rounded-sm shrink-0" />
          </div>
          {/* New Project button */}
          <SidebarNavRowSkeleton labelWidth="w-20" />
          {/* Project items — titles are entity names (truncate text-13 font-serif) */}
          <div className="space-y-px">
            {Array.from({ length: PANEL_ROW_SKELETON_COUNT }, (_, i) => (
              <div
                key={i}
                className="flex items-center gap-3 px-[9px] h-10 rounded-[10px]"
              >
                <div className="skeleton-line size-5 rounded shrink-0" />
                <div
                  className="skeleton-line h-[13px] rounded-md flex-1 font-serif"
                  style={{ width: i === 0 ? "75%" : i === 1 ? "60%" : "85%" }}
                />
              </div>
            ))}
          </div>

          {/* Separator */}
          <div className="h-px bg-stone-200/60 dark:bg-stone-700/40 mx-2 my-1" />

          {/* Section header — Scheduled Tasks */}
          <div className="mt-1 flex items-center justify-between px-[9px] h-9">
            <div className="skeleton-line h-3 w-20 rounded-md" />
            <div className="skeleton-line size-3.5 rounded-sm shrink-0" />
          </div>
          {/* Create Task button */}
          <SidebarNavRowSkeleton labelWidth="w-18" />
          {/* Scheduled task items */}
          <div className="space-y-px">
            {Array.from({ length: PANEL_ROW_SKELETON_COUNT }, (_, i) => (
              <div
                key={`st-${i}`}
                className="flex items-center gap-3 px-[9px] h-10 rounded-[10px]"
              >
                <div className="skeleton-line size-5 rounded shrink-0" />
                <div
                  className="skeleton-line h-[13px] rounded-md flex-1"
                  style={{ width: i === 0 ? "70%" : i === 1 ? "80%" : "60%" }}
                />
              </div>
            ))}
          </div>

          {/* Separator */}
          <div className="h-px bg-stone-200/60 dark:bg-stone-700/40 mx-2 my-1" />

          {/* Section header — Chats */}
          <div className="mt-1 flex items-center justify-between px-[9px] h-9">
            <div className="skeleton-line h-3 w-12 rounded-md" />
            <div className="skeleton-line size-3.5 rounded-sm shrink-0" />
          </div>
          {/* Chat items — session titles are entity names (truncate text-13 font-serif) */}
          <div className="space-y-px">
            {Array.from({ length: PANEL_ROW_SKELETON_COUNT }, (_, i) => (
              <div
                key={i}
                className="flex items-center gap-2 px-[9px] h-10 rounded-[10px]"
              >
                <div
                  className="skeleton-line h-[13px] rounded-md flex-1 font-serif"
                  style={{
                    width:
                      i % 4 === 0
                        ? "70%"
                        : i % 4 === 1
                          ? "85%"
                          : i % 4 === 2
                            ? "55%"
                            : "65%",
                  }}
                />
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Bottom user area */}
      <div className="shrink-0 px-2 py-1 border-t border-stone-300/70 dark:border-stone-800/60">
        <div className="flex items-center gap-3 px-2 py-3 rounded-xl">
          <div className="skeleton-line size-8 rounded-full shrink-0 ring-1 ring-stone-200 dark:ring-stone-700" />
          <div className="flex-1 min-w-0">
            <div className="skeleton-line h-3.5 w-16 rounded-md" />
            <div className="skeleton-line h-3 w-12 rounded-md mt-1" />
          </div>
          <div className="skeleton-line size-4 rounded-sm shrink-0" />
        </div>
      </div>
    </div>
  );
}

function SidebarRailIconSkeleton() {
  return <div className="skeleton-line size-8 rounded-full mx-2" />;
}

function SidebarNavRowSkeleton({
  labelWidth,
  trailing,
}: {
  labelWidth: string;
  trailing?: ReactNode;
}) {
  return (
    <div className="w-full h-8 rounded-[10px] flex items-center gap-3 px-[9px]">
      <div className="skeleton-line size-5 rounded-md shrink-0" />
      <div className={`skeleton-line h-3.5 ${labelWidth} rounded-md`} />
      {trailing}
    </div>
  );
}
