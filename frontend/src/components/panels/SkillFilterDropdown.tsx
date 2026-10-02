import { createPortal } from "react-dom";
import {
  useEffect,
  useId,
  useRef,
  type CSSProperties,
  type ReactNode,
} from "react";
import { ChevronDown } from "lucide-react";
import { useStickyDropdownPosition } from "../../hooks/useStickyDropdownPosition";
import { restoreOpenerFocusUnclaimed } from "../../utils/modalDialog";

export interface SkillFilterOption<T extends string> {
  value: T;
  label: string;
}

interface SkillFilterDropdownProps<T extends string> {
  isOpen: boolean;
  label: string;
  icon?: ReactNode;
  activeCount: number;
  options?: Array<SkillFilterOption<T>>;
  value?: T;
  tags: string[];
  selectedTags: string[];
  tagsLabel: string;
  clearLabel: string;
  onOpenChange: (open: boolean) => void;
  onValueChange?: (value: T) => void;
  onToggleTag: (tag: string) => void;
  onClearFilters: () => void;
}

const DROPDOWN_GUTTER = 12;
const FILTER_DROPDOWN_WIDTH = 288;

function getViewportBounds() {
  const visualViewport = window.visualViewport;
  return {
    width: visualViewport?.width ?? window.innerWidth,
    height: visualViewport?.height ?? window.innerHeight,
    offsetTop: visualViewport?.offsetTop ?? 0,
    offsetLeft: visualViewport?.offsetLeft ?? 0,
  };
}

function getDropdownPosition(rect: DOMRect, width: number): CSSProperties {
  const viewport = getViewportBounds();
  const availableWidth = viewport.width - DROPDOWN_GUTTER * 2;
  const renderedWidth = Math.min(width, availableWidth);
  const minLeft = viewport.offsetLeft + DROPDOWN_GUTTER;
  const maxLeft =
    viewport.offsetLeft + viewport.width - renderedWidth - DROPDOWN_GUTTER;
  const left = Math.min(Math.max(minLeft, rect.right - renderedWidth), maxLeft);
  const below =
    viewport.offsetTop + viewport.height - rect.bottom - 8 - DROPDOWN_GUTTER;
  const above = rect.top - viewport.offsetTop - 8 - DROPDOWN_GUTTER;
  const preferBelow = below >= 160 || below >= above;

  return {
    top: preferBelow ? rect.bottom + 8 : undefined,
    bottom: preferBelow ? undefined : window.innerHeight - rect.top + 8,
    left,
    width: renderedWidth,
    maxHeight: Math.max(0, preferBelow ? below : above),
  };
}

function cx(...classes: Array<string | false | null | undefined>) {
  return classes.filter(Boolean).join(" ");
}

export function SkillFilterDropdown<T extends string>({
  isOpen,
  label,
  icon,
  activeCount,
  options,
  value,
  tags,
  selectedTags,
  tagsLabel,
  clearLabel,
  onOpenChange,
  onValueChange,
  onToggleTag,
  onClearFilters,
}: SkillFilterDropdownProps<T>) {
  const triggerRef = useRef<HTMLButtonElement | null>(null);
  const menuRef = useRef<HTMLDivElement | null>(null);
  const menuId = useId();
  const hasActiveFilters = activeCount > 0;

  const dropdownStyle = useStickyDropdownPosition(triggerRef, isOpen, (rect) =>
    getDropdownPosition(rect, FILTER_DROPDOWN_WIDTH),
  );

  const ready = isOpen && Object.keys(dropdownStyle).length > 0;
  useEffect(() => {
    if (!ready) return;
    const menu = menuRef.current;
    const trigger = triggerRef.current;
    (
      menu?.querySelector<HTMLButtonElement>(
        '[role="menuitemradio"][aria-checked="true"]',
      ) ?? menu?.querySelector<HTMLButtonElement>("button")
    )?.focus();
    return () => {
      if (menu?.contains(document.activeElement))
        queueMicrotask(() => restoreOpenerFocusUnclaimed(trigger, menu));
    };
  }, [ready]);

  const panel = ready
    ? createPortal(
        <div
          className="fixed inset-0 z-[999]"
          data-panel-header-dropdown
          onPointerDown={() => onOpenChange(false)}
        >
          <div
            ref={menuRef}
            id={menuId}
            className="skill-filter-dropdown panel-header-dropdown fixed overflow-y-auto rounded-2xl border bg-[var(--skill-surface)] p-3 shadow-lg"
            role="menu"
            aria-label={label}
            tabIndex={-1}
            style={dropdownStyle}
            onPointerDown={(event) => event.stopPropagation()}
            onKeyDown={(event) => {
              if (
                event.defaultPrevented ||
                event.nativeEvent.isComposing ||
                event.keyCode === 229
              )
                return;
              event.stopPropagation();
              if (event.key === "Escape" || event.key === "Tab") {
                if (event.key === "Escape") event.preventDefault();
                restoreOpenerFocusUnclaimed(
                  triggerRef.current,
                  menuRef.current,
                );
                onOpenChange(false);
                return;
              }
              const items = Array.from(
                menuRef.current?.querySelectorAll<HTMLButtonElement>(
                  "button:not(:disabled)",
                ) ?? [],
              );
              if (!items.length) return;
              const index = items.indexOf(
                document.activeElement as HTMLButtonElement,
              );
              const next =
                event.key === "ArrowDown"
                  ? (index + 1) % items.length
                  : event.key === "ArrowUp"
                    ? index <= 0
                      ? items.length - 1
                      : index - 1
                    : event.key === "Home"
                      ? 0
                      : event.key === "End"
                        ? items.length - 1
                        : -1;
              if (next >= 0) {
                event.preventDefault();
                items[next].focus();
              }
            }}
          >
            {options && options.length > 0 && value && onValueChange && (
              <div className="skill-filter-segment mb-3">
                {options.map((option) => (
                  <button
                    key={option.value}
                    type="button"
                    role="menuitemradio"
                    aria-checked={value === option.value}
                    onClick={() => onValueChange(option.value)}
                    className={cx(
                      "skill-filter-segment__item",
                      value === option.value &&
                        "skill-filter-segment__item--active",
                    )}
                  >
                    {option.label}
                  </button>
                ))}
              </div>
            )}

            {tags.length > 0 && (
              <>
                <div className="mb-2 flex items-center justify-between">
                  <p className="text-12 font-semibold uppercase tracking-[0.16em] text-[var(--theme-text-secondary)]">
                    {tagsLabel}
                  </p>
                  {hasActiveFilters && (
                    <button
                      type="button"
                      role="menuitem"
                      onClick={() => {
                        menuRef.current?.focus();
                        onClearFilters();
                      }}
                      className="text-12 text-[var(--theme-text-secondary)] transition-colors hover:text-[var(--theme-primary)]"
                    >
                      {clearLabel}
                    </button>
                  )}
                </div>
                <div className="flex max-h-56 flex-wrap gap-2 overflow-y-auto">
                  {tags.map((tag) => (
                    <button
                      key={tag}
                      type="button"
                      role="menuitemcheckbox"
                      aria-checked={selectedTags.includes(tag)}
                      onClick={() => onToggleTag(tag)}
                      className={cx(
                        "skill-tag-chip",
                        selectedTags.includes(tag) && "skill-tag-chip--active",
                      )}
                    >
                      {tag}
                    </button>
                  ))}
                </div>
              </>
            )}
          </div>
        </div>,
        document.body,
      )
    : null;

  return (
    <>
      <button
        ref={triggerRef}
        type="button"
        aria-haspopup="menu"
        aria-controls={isOpen ? menuId : undefined}
        aria-expanded={isOpen}
        onClick={() => onOpenChange(!isOpen)}
        className={cx(
          "ui-button ui-button--secondary ui-button--md panel-filter-trigger h-10 px-3",
          hasActiveFilters &&
            "border-[var(--theme-primary)] text-[var(--theme-text)]",
        )}
      >
        {icon}
        <span className="panel-filter-trigger__label">{label}</span>
        {hasActiveFilters && (
          <span className="inline-flex h-5 min-w-5 items-center justify-center rounded-full bg-[var(--theme-primary-light)] px-1 text-11">
            {activeCount}
          </span>
        )}
        <ChevronDown
          size={16}
          className={cx("transition-transform", isOpen && "rotate-180")}
        />
      </button>
      {panel}
    </>
  );
}
