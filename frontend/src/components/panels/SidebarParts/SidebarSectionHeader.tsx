import { useId, useRef, useState, type ReactNode } from "react";
import { Tooltip } from "../../common/Tooltip";
import { ChevronDown, MoreHorizontal, Plus } from "lucide-react";
import { useStickyDropdownPosition } from "../../../hooks/useStickyDropdownPosition";

/** 分组头部动作的显隐节奏：hover/聚焦分组行时浮现，触屏设备常显。 */
export const sectionRevealClass =
  "opacity-0 group-hover/section:opacity-100 group-focus-within/section:opacity-100 [@media(hover:none)]:opacity-100";
/** 分组头部动作按钮（+、⋯、多选等）的统一样式。 */
export const sectionActionClass =
  "inline-flex size-7 shrink-0 items-center justify-center rounded-md text-stone-500 hover:bg-stone-100 hover:text-stone-700 dark:text-stone-400 dark:hover:bg-stone-800/60 dark:hover:text-stone-200 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2";

export function SidebarSectionHeader({
  label,
  collapsed,
  onToggle,
  createLabel,
  onCreate,
  moreLabel,
  menuItems,
  children,
}: {
  label: string;
  collapsed: boolean;
  onToggle: () => void;
  createLabel: string;
  onCreate?: () => void;
  moreLabel: string;
  menuItems: { label: string; onClick: () => void }[];
  children?: ReactNode;
}) {
  const menuId = useId();
  const triggerRef = useRef<HTMLButtonElement>(null);
  const menuRef = useRef<HTMLDivElement>(null);
  const [open, setOpen] = useState(false);
  const menuStyle = useStickyDropdownPosition(triggerRef, open, (rect) => ({
    top: Math.max(8, Math.min(rect.bottom + 4, window.innerHeight - 160)),
    left: Math.max(8, Math.min(rect.right - 192, window.innerWidth - 200)),
  }));

  return (
    <div className="group/section flex h-9 items-center gap-1 px-[9px] select-none">
      <button
        type="button"
        onClick={onToggle}
        aria-expanded={!collapsed}
        className="flex min-w-0 flex-1 items-center gap-2 self-stretch text-13 font-medium text-stone-400 dark:text-stone-500 group-hover/section:text-stone-500 dark:group-hover/section:text-stone-400 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2"
      >
        <span className="truncate">{label}</span>
        <ChevronDown
          size={14}
          aria-hidden="true"
          className={`shrink-0 transition-transform motion-reduce:transition-none ${
            open ? "opacity-100" : sectionRevealClass
          } ${collapsed ? "-rotate-90" : ""}`}
        />
      </button>
      {children}
      <div
        className={`flex shrink-0 items-center gap-1 ${
          open ? "opacity-100" : sectionRevealClass
        }`}
      >
        {onCreate && (
          <Tooltip content={createLabel}>
            <button
              type="button"
              onClick={onCreate}
              aria-label={createLabel}
              className={sectionActionClass}
            >
              <Plus size={14} />
            </button>
          </Tooltip>
        )}
        <Tooltip content={moreLabel}>
          <button
            ref={triggerRef}
            type="button"
            popoverTarget={menuId}
            aria-label={moreLabel}
            className={sectionActionClass}
          >
            <MoreHorizontal size={14} />
          </button>
        </Tooltip>
      </div>
      <div
        ref={menuRef}
        id={menuId}
        popover="auto"
        onToggle={(event) => setOpen(event.newState === "open")}
        style={menuStyle}
        className="fixed inset-auto m-0 w-48 rounded-xl border border-theme-border bg-theme-bg-card p-1 text-theme-text shadow-xl"
      >
        {menuItems.map((item) => (
          <button
            key={item.label}
            type="button"
            className="sidebar-nav-btn flex min-h-8 w-full items-center rounded-lg px-2 text-left text-13 focus-visible:outline focus-visible:outline-2"
            onClick={() => {
              menuRef.current?.hidePopover?.();
              item.onClick();
            }}
          >
            {item.label}
          </button>
        ))}
      </div>
    </div>
  );
}
