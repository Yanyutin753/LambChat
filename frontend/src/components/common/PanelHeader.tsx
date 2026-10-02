/**
 * 统一的面板头部组件
 * 用于所有管理面板的标题和操作区域
 */

import {
  Children,
  Fragment,
  isValidElement,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { useTranslation } from "react-i18next";
import { MoreHorizontal, Search } from "lucide-react";
import { SceneIllustration, type IllustrationScene } from "./SceneIllustration";
import { PanelSearchInput } from "./PanelSearchInput";
import { restoreOpenerFocusUnclaimed } from "../../utils/modalDialog";

interface PanelHeaderProps {
  /** 面板标题 */
  title: string;
  count?: number;
  /** 副标题/描述 */
  subtitle?: string;
  /** 标题图标 */
  icon?: ReactNode;
  /** 场景插图优先于标题图标 */
  illustration?: IllustrationScene;
  /** 右侧操作按钮区域 */
  actions?: ReactNode;
  /** 搜索值 */
  searchValue?: string;
  /** 搜索变化回调 */
  onSearchChange?: (value: string) => void;
  /** 搜索占位符 */
  searchPlaceholder?: string;
  /** 搜索区域右侧附加控件 */
  searchAccessory?: ReactNode;
  /** 搜索区域右侧操作按钮 */
  searchActions?: ReactNode;
  /** 只渲染搜索行，用于嵌入式子面板 */
  searchOnly?: boolean;
  /** 额外的头部内容 */
  children?: ReactNode;
  /** 额外 class */
  className?: string;
}

function flattenActionNodes(node: ReactNode): ReactNode[] {
  return Children.toArray(node).flatMap((child) => {
    if (isValidElement(child) && child.type === Fragment) {
      return flattenActionNodes(
        (child.props as { children?: ReactNode }).children,
      );
    }
    return child;
  });
}

export function PanelHeader({
  title,
  count,
  subtitle,
  icon,
  illustration,
  actions,
  searchValue,
  onSearchChange,
  searchPlaceholder,
  searchAccessory,
  searchActions,
  searchOnly = false,
  children,
  className,
}: PanelHeaderProps) {
  const { t } = useTranslation();
  const actionNodes = useMemo(() => flattenActionNodes(actions), [actions]);
  const searchActionNodes = useMemo(
    () => flattenActionNodes(searchActions),
    [searchActions],
  );
  const mobileMenuRef = useRef<HTMLDivElement>(null);
  const [isMobileMenuOpen, setIsMobileMenuOpen] = useState(false);
  const hasSearch = onSearchChange !== undefined;
  const mobileActionNodes = hasSearch
    ? [...actionNodes, ...searchActionNodes]
    : actionNodes;
  const hasMobileMenuContent =
    mobileActionNodes.length > 0 || Boolean(searchAccessory);

  useEffect(() => {
    if (!isMobileMenuOpen) return;

    const handlePointerDown = (event: PointerEvent) => {
      const target = event.target as Node;
      if (
        target instanceof Element &&
        (target.closest("[data-panel-header-dropdown]") ||
          target.closest(".ui-select-dropdown"))
      ) {
        return;
      }

      if (mobileMenuRef.current && !mobileMenuRef.current.contains(target)) {
        setIsMobileMenuOpen(false);
      }
    };

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.defaultPrevented || event.isComposing || event.keyCode === 229)
        return;
      if (event.key === "Escape") {
        setIsMobileMenuOpen(false);
        mobileMenuRef.current
          ?.querySelector<HTMLButtonElement>("button")
          ?.focus();
      }
    };
    document.addEventListener("pointerdown", handlePointerDown);
    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("pointerdown", handlePointerDown);
      document.removeEventListener("keydown", handleKeyDown);
    };
  }, [isMobileMenuOpen]);

  const rootClassName = [
    "panel-header",
    className,
    hasSearch ? "panel-header--has-search" : "",
    searchOnly ? "panel-header--search-only" : "",
  ]
    .filter(Boolean)
    .join(" ");

  const mobileMenu = isMobileMenuOpen && (
    <div className="panel-header__mobile-menu">
      {searchAccessory && (
        <div className="panel-header__mobile-menu-section panel-header__mobile-menu-accessory">
          {searchAccessory}
        </div>
      )}
      {mobileActionNodes.map((action, index) => (
        <div
          key={index}
          className="panel-header__mobile-menu-item"
          onClick={(e) => {
            if ((e.target as Element).closest(".ui-select, [data-filter-menu]"))
              return;
            restoreOpenerFocusUnclaimed(
              mobileMenuRef.current?.querySelector<HTMLButtonElement>("button"),
              mobileMenuRef.current,
            );
            setIsMobileMenuOpen(false);
          }}
        >
          {action}
        </div>
      ))}
    </div>
  );

  return (
    <div className={rootClassName}>
      {!searchOnly && (
        <div className="panel-header__top flex flex-wrap items-center justify-between gap-3 lg:gap-4">
          <div className="panel-header__identity flex min-w-0 items-center gap-3 lg:gap-4">
            {illustration ? (
              <div className="panel-header__icon panel-header__illustration">
                <SceneIllustration scene={illustration} />
              </div>
            ) : (
              icon && <div className="panel-header__icon">{icon}</div>
            )}
            <div className="min-w-0">
              <div className="flex min-w-0 items-center gap-2">
                <h1 className="panel-header__title truncate text-16 font-semibold text-theme-text lg:text-18 font-serif">
                  {title}
                </h1>
                {count !== undefined && (
                  <span className="panel-header__count text-11 font-sans font-normal text-theme-text-tertiary">
                    {count}
                  </span>
                )}
              </div>
              {subtitle && (
                <p className="panel-header__subtitle mt-0.5 truncate text-14 leading-snug text-theme-text-secondary lg:text-[0.85rem]">
                  {subtitle}
                </p>
              )}
            </div>
          </div>
          {actionNodes.length > 0 && (
            <div className="panel-header__actions panel-header__desktop-actions flex flex-nowrap flex-shrink-0 items-center gap-1.5 sm:gap-2">
              {actions}
            </div>
          )}
          {hasMobileMenuContent && !hasSearch && (
            <div className="panel-header__mobile-actions" ref={mobileMenuRef}>
              <button
                type="button"
                className="panel-header__mobile-more"
                title={t("common.filtersAndActions")}
                aria-label={t("common.filtersAndActions")}
                aria-expanded={isMobileMenuOpen}
                onClick={() => setIsMobileMenuOpen((prev) => !prev)}
              >
                <MoreHorizontal size={22} />
              </button>
              {mobileMenu}
            </div>
          )}
        </div>
      )}

      {/* 搜索框 */}
      {onSearchChange !== undefined && (
        <div className="panel-header__search-row mt-2 flex items-center gap-2 sm:mt-3 lg:mt-4">
          <div className="panel-header__search-box relative min-w-0 flex-1">
            <Search
              size={18}
              className="absolute left-3 top-1/2 -translate-y-1/2 text-theme-text-tertiary"
            />
            <PanelSearchInput
              type="text"
              value={searchValue}
              onValueChange={onSearchChange}
              className="panel-search h-10"
              placeholder={searchPlaceholder}
            />
            {hasMobileMenuContent && (
              <div
                className="panel-header__mobile-actions panel-header__mobile-actions--search"
                ref={mobileMenuRef}
              >
                <button
                  type="button"
                  className="panel-header__mobile-more panel-header__mobile-more--inline"
                  title={t("common.filtersAndActions")}
                  aria-label={t("common.filtersAndActions")}
                  aria-expanded={isMobileMenuOpen}
                  onClick={() => setIsMobileMenuOpen((prev) => !prev)}
                >
                  <MoreHorizontal size={22} />
                </button>
                {mobileMenu}
              </div>
            )}
          </div>
          {searchAccessory && !isMobileMenuOpen && (
            <div className="panel-header__search-accessory">
              {searchAccessory}
            </div>
          )}
          {searchActionNodes.length > 0 && (
            <div className="panel-header__search-actions flex flex-nowrap shrink-0 items-center gap-1.5 sm:gap-2">
              {searchActions}
            </div>
          )}
        </div>
      )}

      {/* 额外内容 */}
      {children}
    </div>
  );
}

export default PanelHeader;
