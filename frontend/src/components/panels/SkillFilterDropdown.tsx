import { createPortal } from "react-dom";
import { useId, useRef, type ReactNode } from "react";
import { ChevronDown } from "lucide-react";
import { usePanelFilterMenu } from "../../hooks/usePanelFilterMenu";

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
  const menuId = useId();
  const hasActiveFilters = activeCount > 0;

  const { menuRef, dropdownStyle, ready, onKeyDown, closeMenu } =
    usePanelFilterMenu(triggerRef, isOpen, 288, () => onOpenChange(false));

  const panel = ready
    ? createPortal(
        <div
          className="fixed inset-0 z-[999]"
          data-panel-header-dropdown
          onPointerDown={closeMenu}
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
            onKeyDown={onKeyDown}
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
