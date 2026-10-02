import { createPortal } from "react-dom";
import { useTranslation } from "react-i18next";
import { usePanelFilterMenu } from "../../hooks/usePanelFilterMenu";

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

  const { menuRef, dropdownStyle, ready, onKeyDown, closeMenu } =
    usePanelFilterMenu(tagBtnRef, isOpen, 288, onClose);

  if (!ready) return null;

  return createPortal(
    <div
      className="fixed inset-0 z-[999]"
      data-panel-header-dropdown
      onPointerDown={closeMenu}
    >
      <div
        className="skill-filter-dropdown panel-header-dropdown fixed overflow-y-auto rounded-2xl border bg-[var(--skill-surface)] p-3 shadow-lg"
        ref={menuRef}
        tabIndex={-1}
        onKeyDown={onKeyDown}
        role="menu"
        aria-label={t("personaPresets.tags")}
        style={dropdownStyle}
        onPointerDown={(e) => e.stopPropagation()}
      >
        <div className="mb-2 flex items-center justify-between">
          <p className="text-12 font-semibold uppercase tracking-[0.16em] text-[var(--theme-text-secondary)]">
            {t("personaPresets.tags", "标签")}
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
              role="menuitemradio"
              aria-checked={activeTag === tag}
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
