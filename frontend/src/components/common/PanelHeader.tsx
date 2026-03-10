/**
 * 统一的面板头部组件
 * 用于所有管理面板的标题和操作区域
 */

import { type ReactNode } from "react";
import { Search } from "lucide-react";

interface PanelHeaderProps {
  /** 面板标题 */
  title: string;
  /** 副标题/描述 */
  subtitle?: string;
  /** 标题图标 */
  icon?: ReactNode;
  /** 右侧操作按钮区域 */
  actions?: ReactNode;
  /** 搜索值 */
  searchValue?: string;
  /** 搜索变化回调 */
  onSearchChange?: (value: string) => void;
  /** 搜索占位符 */
  searchPlaceholder?: string;
  /** 额外的头部内容 */
  children?: ReactNode;
}

export function PanelHeader({
  title,
  subtitle,
  icon,
  actions,
  searchValue,
  onSearchChange,
  searchPlaceholder,
  children,
}: PanelHeaderProps) {
  return (
    <div className="panel-header">
      <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex min-w-0 items-center gap-3">
          {icon && (
            <div className="flex h-9 w-9 flex-shrink-0 items-center justify-center rounded-lg bg-stone-100 dark:bg-stone-800">
              {icon}
            </div>
          )}
          <div className="min-w-0">
            <h1 className="truncate text-lg font-semibold text-stone-900 dark:text-stone-100 sm:text-xl">
              {title}
            </h1>
            {subtitle && (
              <p className="mt-0.5 truncate text-sm text-stone-500 dark:text-stone-400">
                {subtitle}
              </p>
            )}
          </div>
        </div>
        {actions && (
          <div className="flex flex-shrink-0 gap-1.5 sm:gap-2">
            {actions}
          </div>
        )}
      </div>

      {/* 搜索框 */}
      {onSearchChange !== undefined && (
        <div className="relative mt-2 sm:mt-3">
          <Search
            size={18}
            className="absolute left-3 top-1/2 -translate-y-1/2 text-stone-400 dark:text-stone-500"
          />
          <input
            type="text"
            value={searchValue}
            onChange={(e) => onSearchChange(e.target.value)}
            className="panel-search"
            placeholder={searchPlaceholder}
          />
        </div>
      )}

      {/* 额外内容 */}
      {children}
    </div>
  );
}

export default PanelHeader;
