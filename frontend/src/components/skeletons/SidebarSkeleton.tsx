import type { ReactNode } from "react";
import "../../styles/desktop.css";

import { SIDEBAR_COLLAPSED_STORAGE_KEY } from "../../hooks/useAuth";
import { PANEL_ROW_SKELETON_COUNT } from "./PanelSkeletonHelpers";

/** Sidebar skeleton — matches real SessionSidebar layout */
export function SidebarSkeleton() {
  const collapsed = (() => {
    const saved = localStorage.getItem(SIDEBAR_COLLAPSED_STORAGE_KEY);
    return saved !== null ? saved === "true" : false;
  })();

  return (
    <div
      data-desktop-sidebar-shell=""
      className="hidden sm:flex h-full shrink-0"
      aria-hidden="true"
    >
      <SidebarRailSkeleton />
      {!collapsed && <SidebarExpandedSkeleton />}
    </div>
  );
}

/** The activity rail stays visible when the conversation list collapses. */
function SidebarRailSkeleton() {
  return (
    <div
      data-desktop-activity-rail=""
      className="flex h-full w-[var(--sidebar-rail-width)] shrink-0 flex-col items-center border-r border-theme-border bg-[var(--theme-bg-sidebar)] py-1.5"
      style={{
        paddingTop:
          "calc((var(--workspace-header-height, 3rem) - 2.25rem) / 2)",
      }}
    >
      <div className="flex min-h-0 flex-1 flex-col items-center gap-2 overflow-y-auto">
        {Array.from({ length: 8 }, (_, i) => (
          <SidebarRailIconSkeleton key={i} />
        ))}
      </div>
      <div className="flex size-9 shrink-0 items-center justify-center">
        <div className="skeleton-line size-8 rounded-full" />
      </div>
    </div>
  );
}

/** Skeleton for the expanded sidebar */
function SidebarExpandedSkeleton() {
  return (
    <div
      data-desktop-sidebar=""
      className="flex w-[264px] shrink-0 flex-col overflow-hidden bg-[var(--theme-bg-sidebar)] border-r border-theme-border"
    >
      {/* Header area — app icon (h-7) + name + collapse button */}
      <div className="flex h-12 shrink-0 items-center justify-between ps-[13px] pe-[7px]">
        <div className="flex h-7 items-center gap-1.5">
          <div className="skeleton-line size-7 rounded-full shrink-0" />
          <div className="skeleton-line h-7 w-20 rounded-md" />
        </div>
        <div className="skeleton-line size-8 rounded-lg shrink-0" />
      </div>

      {/* Conversation actions — New Chat and Search */}
      <div className="flex flex-col gap-px px-2 mb-2 space-y-1">
        {/* New Chat */}
        <SidebarNavRowSkeleton labelWidth="w-16" />
        {/* Search */}
        <SidebarNavRowSkeleton
          labelWidth="w-14 flex-1"
          trailing={<div className="skeleton-line h-4 w-10 rounded-md" />}
        />
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
    </div>
  );
}

function SidebarRailIconSkeleton() {
  return (
    <div
      data-rail-icon=""
      className="flex size-9 shrink-0 items-center justify-center rounded-[var(--radius-lg)]"
    >
      <div className="skeleton-line size-5 rounded-md" />
    </div>
  );
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
