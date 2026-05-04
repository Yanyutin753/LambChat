import { createPortal } from "react-dom";
import { useTranslation } from "react-i18next";

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

  if (!isOpen || !tagBtnRef.current) return null;

  return createPortal(
    <div className="fixed inset-0 z-[999]" onMouseDown={onClose}>
      <div
        className="skill-filter-dropdown absolute w-72 rounded-2xl border bg-[var(--skill-surface)] p-3 shadow-lg"
        style={{
          top: tagBtnRef.current.getBoundingClientRect().bottom + 8,
          right:
            window.innerWidth - tagBtnRef.current.getBoundingClientRect().right,
        }}
        onMouseDown={(e) => e.stopPropagation()}
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
