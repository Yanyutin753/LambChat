import { useEffect, useRef } from "react";
import { useTranslation } from "react-i18next";
import {
  Plus,
  Package,
  FolderOpen,
  Check,
  Tag,
  ChevronDown,
  Github,
  Archive,
  X,
} from "lucide-react";
import { PanelHeader } from "../../common/PanelHeader";
import { SkillsPanelSkeleton } from "../../skeletons";
import { Pagination } from "../../common/Pagination";
import { SkillCard } from "../../skill/SkillCard";
import type { SkillResponse } from "../../../types";

interface SkillsListProps {
  searchQuery: string;
  setSearchQuery: (query: string) => void;
  selectedTags: string[];
  isFilterOpen: boolean;
  setIsFilterOpen: React.Dispatch<React.SetStateAction<boolean>>;
  availableTags: string[];
  filteredSkills: SkillResponse[];
  paginatedSkills: SkillResponse[];
  total: number;
  page: number;
  pageSize: number;
  setPage: (page: number) => void;
  toggleTag: (tag: string) => void;
  clearFilters: () => void;
  isLoading: boolean;
  error: string | null;
  clearError: () => void;
  canWrite: boolean;
  canPublish: boolean;
  selectedNames: Set<string>;
  onToggle: (name: string) => void;
  onEdit: (skill: SkillResponse) => void;
  onDelete: (name: string) => void;
  onExportZip: (name: string) => void;
  onPublish: ((skill: SkillResponse) => void) | undefined;
  onSelectSkill: (name: string) => void;
  onSelectAll: () => void;
  onCreate: () => void;
  onGithubClick: () => void;
  onZipClick: () => void;
}

export function SkillsList({
  searchQuery,
  setSearchQuery,
  selectedTags,
  isFilterOpen,
  setIsFilterOpen,
  availableTags,
  filteredSkills,
  paginatedSkills,
  total,
  page,
  pageSize,
  setPage,
  toggleTag,
  clearFilters,
  isLoading,
  error,
  clearError,
  canWrite,
  canPublish,
  selectedNames,
  onToggle,
  onEdit,
  onDelete,
  onExportZip,
  onPublish,
  onSelectSkill,
  onSelectAll,
  onCreate,
  onGithubClick,
  onZipClick,
}: SkillsListProps) {
  const { t } = useTranslation();
  const filterRef = useRef<HTMLDivElement>(null);

  // Close filter dropdown when clicking outside
  useEffect(() => {
    if (!isFilterOpen) return;
    const handleClick = (e: MouseEvent) => {
      if (filterRef.current && !filterRef.current.contains(e.target as Node)) {
        setIsFilterOpen(false);
      }
    };
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, [isFilterOpen, setIsFilterOpen]);

  if (isLoading) {
    return <SkillsPanelSkeleton />;
  }

  const hasActiveFilters =
    searchQuery.trim().length > 0 || selectedTags.length > 0;

  return (
    <>
      {/* Header */}
      <PanelHeader
        title={t("skills.title")}
        subtitle={t("skills.subtitle")}
        icon={
          <Package size={20} className="text-stone-600 dark:text-stone-400" />
        }
        searchValue={searchQuery}
        onSearchChange={setSearchQuery}
        searchPlaceholder={t("skills.searchPlaceholder")}
        searchAccessory={
          availableTags.length > 0 ? (
            <div className="relative shrink-0" ref={filterRef}>
              <button
                type="button"
                onClick={() => setIsFilterOpen((prev) => !prev)}
                className={`btn-secondary h-10 px-3 ${
                  selectedTags.length > 0
                    ? "border-[var(--theme-primary)] text-[var(--theme-text)]"
                    : ""
                }`}
              >
                <Tag size={14} />
                <span className="hidden sm:inline">
                  {t("adminMarketplace.tags")}
                </span>
                {selectedTags.length > 0 && (
                  <span className="inline-flex h-5 min-w-5 items-center justify-center rounded-full bg-[var(--theme-primary-light)] px-1 text-[11px]">
                    {selectedTags.length}
                  </span>
                )}
                <ChevronDown
                  size={14}
                  className={`transition-transform ${
                    isFilterOpen ? "rotate-180" : ""
                  }`}
                />
              </button>
              {isFilterOpen && (
                <div className="skill-filter-dropdown absolute right-0 top-[calc(100%+0.5rem)] z-20 w-72 rounded-2xl border  p-3 shadow-lg">
                  <div className="mb-2 flex items-center justify-between">
                    <p className="text-xs font-semibold uppercase tracking-[0.16em] text-[var(--theme-text-secondary)]">
                      {t("adminMarketplace.tags")}
                    </p>
                    {hasActiveFilters && (
                      <button
                        type="button"
                        onClick={clearFilters}
                        className="text-xs text-[var(--theme-text-secondary)] transition-colors hover:text-[var(--theme-primary)]"
                      >
                        {t("marketplace.clearFilters")}
                      </button>
                    )}
                  </div>
                  <div className="flex max-h-56 flex-wrap gap-2 overflow-y-auto">
                    {availableTags.map((tag) => (
                      <button
                        key={tag}
                        type="button"
                        onClick={() => toggleTag(tag)}
                        className={`skill-tag-chip ${
                          selectedTags.includes(tag)
                            ? "skill-tag-chip--active"
                            : ""
                        }`}
                      >
                        {tag}
                      </button>
                    ))}
                  </div>
                </div>
              )}
            </div>
          ) : null
        }
        actions={
          <div className="flex items-center gap-2">
            {filteredSkills.length > 0 && (
              <button onClick={onSelectAll} className="btn-secondary">
                <Check size={16} />
                <span className="hidden sm:inline">
                  {selectedNames.size === filteredSkills.length &&
                  filteredSkills.length > 0
                    ? t("common.deselectAll")
                    : t("common.selectAll")}
                </span>
              </button>
            )}
            <button onClick={onGithubClick} className="btn-secondary">
              <Github size={16} />
              <span className="hidden sm:inline">GitHub</span>
            </button>
            <button onClick={onZipClick} className="btn-secondary">
              <Archive size={16} />
              <span className="hidden sm:inline">ZIP</span>
            </button>
            <button onClick={onCreate} className="btn-primary">
              <Plus size={16} />
              <span className="hidden sm:inline">{t("skills.newSkill")}</span>
            </button>
          </div>
        }
      />

      {/* Error */}
      {error && (
        <div className="mx-4 mt-4 flex items-center justify-between rounded-xl bg-red-50 p-3 text-sm text-red-700 dark:bg-red-900/30 dark:text-red-400">
          <span>{error}</span>
          <button
            onClick={clearError}
            className="btn-icon hover:text-red-900 dark:hover:text-red-300"
          >
            <X size={18} />
          </button>
        </div>
      )}

      {/* Skills List */}
      <div className="skill-content-area flex-1 overflow-y-auto p-2 sm:p-4">
        {filteredSkills.length === 0 ? (
          <div className="skill-empty-state">
            <div className="skill-empty-state__icon">
              <FolderOpen size={28} />
            </div>
            <p className="skill-empty-state__title">
              {hasActiveFilters
                ? t("skills.noMatchingSkills")
                : t("skills.noSkills")}
            </p>
            <p className="skill-empty-state__description">
              {hasActiveFilters
                ? t("skills.subtitle")
                : t("skills.createFirst")}
            </p>
            {!hasActiveFilters && canWrite && (
              <button onClick={onCreate} className="btn-primary mt-4">
                <Plus size={16} />
                <span>{t("skills.newSkill")}</span>
              </button>
            )}
            {hasActiveFilters && (
              <button
                type="button"
                onClick={clearFilters}
                className="btn-secondary mt-4"
              >
                {t("marketplace.clearFilters")}
              </button>
            )}
          </div>
        ) : (
          <div className="skill-grid grid grid-cols-1 gap-4 sm:grid-cols-2">
            {paginatedSkills.map((skill) => (
              <SkillCard
                key={skill.name}
                skill={skill}
                onToggle={onToggle}
                onEdit={onEdit}
                onDelete={onDelete}
                onExportZip={onExportZip}
                onPublish={
                  canPublish ? (s: SkillResponse) => onPublish?.(s) : undefined
                }
                isPublished={skill.is_published}
                selected={selectedNames.has(skill.name)}
                onSelect={onSelectSkill}
                selectionMode={true}
              />
            ))}
          </div>
        )}
      </div>

      {/* Pagination */}
      {total > pageSize && (
        <div className="glass-divider px-3 py-3 sm:px-4">
          <Pagination
            page={page}
            pageSize={pageSize}
            total={total}
            onChange={setPage}
          />
        </div>
      )}
    </>
  );
}
