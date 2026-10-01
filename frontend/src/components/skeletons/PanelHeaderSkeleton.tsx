import { type ReactNode } from "react";
import { SkeletonLine } from "./primitives";

/** Mirrors PanelHeader, including container-responsive identity and inline menu. */
export function PanelHeaderSkeleton({
  actions,
  hasSearch = true,
  hasSubtitle = false,
  searchOnly = false,
  hasActions = true,
  hasSearchAccessory = false,
  hasSearchActions = false,
  className = "",
}: {
  actions?: ReactNode;
  hasSearch?: boolean;
  hasSubtitle?: boolean;
  searchOnly?: boolean;
  hasActions?: boolean;
  hasSearchAccessory?: boolean;
  hasSearchActions?: boolean;
  className?: string;
}) {
  const hasMenu = hasActions || hasSearchAccessory || hasSearchActions;
  const mobileMenu = hasMenu && (
    <div
      className={`panel-header__mobile-actions ${
        hasSearch ? "panel-header__mobile-actions--search" : ""
      }`}
    >
      <div
        className={`panel-header__mobile-more ${
          hasSearch ? "panel-header__mobile-more--inline" : ""
        }`}
      >
        <div className="skeleton-line size-5 rounded-md" />
      </div>
    </div>
  );

  return (
    <div
      aria-hidden="true"
      className={`panel-header ${hasSearch ? "panel-header--has-search" : ""} ${
        searchOnly ? "panel-header--search-only" : ""
      } ${className}`}
    >
      {!searchOnly && (
        <div className="panel-header__top flex flex-wrap items-center justify-between gap-3 lg:gap-4">
          <div className="panel-header__identity flex min-w-0 items-center gap-3 lg:gap-4">
            <div className="panel-header__icon panel-header__illustration">
              <div className="skeleton-line size-full rounded-lg" />
            </div>
            <div className="min-w-0">
              <div className="panel-header__title flex h-[1.5em] items-center text-16 lg:text-18">
                <SkeletonLine
                  width="w-28 sm:w-36 xl:w-48"
                  className="!h-4 lg:!h-[18px]"
                />
              </div>
              {hasSubtitle && (
                <div className="panel-header__subtitle mt-0.5 flex h-[1.5em] items-center text-14 leading-snug lg:text-[0.85rem]">
                  <SkeletonLine
                    width="w-40 sm:w-52 xl:w-64"
                    className="!h-3 sm:!h-[14px] !opacity-60"
                  />
                </div>
              )}
            </div>
          </div>
          {hasActions && (
            <div className="panel-header__actions panel-header__desktop-actions flex flex-nowrap flex-shrink-0 items-center gap-1.5 sm:gap-2">
              {actions ?? (
                <>
                  <div className="skeleton-line h-10 w-20 rounded-lg" />
                  <div className="skeleton-line size-10 rounded-lg" />
                </>
              )}
            </div>
          )}
          {!hasSearch && mobileMenu}
        </div>
      )}
      {hasSearch && (
        <div className="panel-header__search-row mt-2 flex items-center gap-2 sm:mt-3 lg:mt-4">
          <div className="panel-header__search-box relative min-w-0 flex-1">
            <div className="skeleton-line h-10 w-full rounded-lg" />
            {mobileMenu}
          </div>
          {hasSearchAccessory && (
            <div className="panel-header__search-accessory">
              <div className="skeleton-line h-10 w-28 rounded-lg" />
            </div>
          )}
          {hasSearchActions && (
            <div className="panel-header__search-actions flex flex-nowrap shrink-0 items-center gap-1.5 sm:gap-2">
              <div className="skeleton-line size-10 rounded-lg" />
            </div>
          )}
        </div>
      )}
    </div>
  );
}
