import type { ReactNode } from "react";
import { Tooltip } from "../../common/Tooltip";
import { ChevronDown, Plus, SquarePen } from "lucide-react";

/** 分组头部动作的显隐节奏：hover/聚焦分组行时浮现，触屏点击分组后显示。 */
export const sectionRevealClass = "sidebar-action-reveal";
/** 分组头部动作按钮（新增、多选等）的统一样式。 */
export const sectionActionClass =
  "inline-flex h-8 w-8 max-sm:h-9 max-sm:w-9 shrink-0 items-center justify-center rounded-md text-stone-500 hover:text-stone-700 dark:text-stone-400 dark:hover:text-stone-200 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2";

export function SidebarSectionHeader({
  label,
  collapsed,
  onToggle,
  createLabel,
  onCreate,
  createIcon = "plus",
  children,
}: {
  label: string;
  collapsed: boolean;
  onToggle: () => void;
  createLabel: string;
  onCreate?: () => void;
  createIcon?: "plus" | "compose";
  children?: ReactNode;
}) {
  return (
    <div className="sidebar-action-row group/section flex h-8 max-sm:h-9 items-center gap-1 px-[9px] select-none">
      <button
        type="button"
        onClick={onToggle}
        aria-expanded={!collapsed}
        className="flex min-w-0 flex-1 items-center gap-2 self-stretch text-14 font-medium text-stone-400 dark:text-stone-500 group-hover/section:text-stone-500 dark:group-hover/section:text-stone-400 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2"
      >
        <span className="truncate">{label}</span>
        <ChevronDown
          size={14}
          aria-hidden="true"
          className={`shrink-0 transition-transform motion-reduce:transition-none ${sectionRevealClass} ${collapsed ? "-rotate-90" : ""}`}
        />
      </button>
      <div
        className={`flex shrink-0 items-center gap-1 sidebar-action-controls ${sectionRevealClass}`}
      >
        {onCreate && (
          <Tooltip content={createLabel}>
            <button
              type="button"
              onClick={onCreate}
              aria-label={createLabel}
              className={sectionActionClass}
            >
              {createIcon === "compose" ? (
                <SquarePen size={14} />
              ) : (
                <Plus size={14} />
              )}
            </button>
          </Tooltip>
        )}
      </div>
      {children}
    </div>
  );
}
