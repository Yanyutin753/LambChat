import { createPortal } from "react-dom";
import { useEffect, type CSSProperties } from "react";
import { useTranslation } from "react-i18next";
import { useStickyDropdownPosition } from "../../hooks/useStickyDropdownPosition";

interface PersonaTagFilterDropdownProps {
  isOpen: boolean;
  allTags: string[];
  activeTag: string | null;
  hasActiveFilters: boolean;
  tagBtnRef: React.RefObject<HTMLButtonElement | null>;
  onToggleTag: (tag: string) => void;
  onClearFilters: () => void;
  onClose: () => void;
}

const DROPDOWN_GUTTER = 12;
const TAG_DROPDOWN_WIDTH = 288;

function getDropdownPosition(rect: DOMRect, width: number): CSSProperties {
  const availableWidth = window.innerWidth - DROPDOWN_GUTTER * 2;
  const renderedWidth = Math.min(width, availableWidth);
  const left = Math.min(
    Math.max(DROPDOWN_GUTTER, rect.right - renderedWidth),
    window.innerWidth - renderedWidth - DROPDOWN_GUTTER,
  );
  const top = rect.bottom + 8;

  return {
    top,
    left,
    width: renderedWidth,
    maxHeight: `calc(100dvh - ${top + DROPDOWN_GUTTER}px)`,
  };
}

export function PersonaTagFilterDropdown({
  isOpen,
  allTags,
  activeTag,
  hasActiveFilters,
  tagBtnRef,
  onToggleTag,
  onClearFilters,
  onClose,
}: PersonaTagFilterDropdownProps) {
  const { t } = useTranslation();

  useEffect(() => {
    if (!isOpen) return;

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [isOpen, onClose]);

  // Compute style before any early return — hooks must not be called conditionally
  const dropdownStyle = useStickyDropdownPosition(tagBtnRef, isOpen, (rect) =>
    getDropdownPosition(rect, TAG_DROPDOWN_WIDTH),
  );

  if (!isOpen) return null;

  return createPortal(
    <div
      className="fixed inset-0 z-[999]"
      data-panel-header-dropdown
      onPointerDown={onClose}
    >
      <div
        className="skill-filter-dropdown panel-header-dropdown fixed overflow-hidden rounded-2xl border bg-[var(--skill-surface)] p-3 shadow-lg"
        role="menu"
        style={dropdownStyle}
        onPointerDown={(e) => e.stopPropagation()}
      >
        <div className="mb-2 flex items-center justify-between">
          <p className="text-xs font-semibold uppercase tracking-[0.16em] text-[var(--theme-text-secondary)]">
            {t("personaPresets.tags", "标签")}
          </p>
          {hasActiveFilters && (
            <button
              type="button"
              onClick={onClearFilters}
              className="text-xs text-[var(--theme-text-secondary)] transition-colors hover:text-[var(--theme-primary)]"
            >
              {t("personaPresets.clearFilters", "清除筛选")}
            </button>
          )}
        </div>
        <div className="flex max-h-56 flex-wrap gap-2 overflow-y-auto">
          {allTags.map((tag) => (
            <button
              key={tag}
              type="button"
              onClick={() => onToggleTag(tag)}
              aria-pressed={activeTag === tag}
              className={`skill-tag-chip ${
                activeTag === tag ? "skill-tag-chip--active" : ""
              }`}
            >
              {tag}
            </button>
          ))}
        </div>
      </div>
    </div>,
    document.body,
  );
}
