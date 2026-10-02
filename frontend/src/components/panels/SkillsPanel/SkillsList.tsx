import { useState } from "react";
import { useTranslation } from "react-i18next";
import { FolderOpen, Plus, Check, Github, Archive, X } from "lucide-react";
import { PanelHeader } from "../../common/PanelHeader";
import { SkillsListSkeleton, SkillsPanelSkeleton } from "../../skeletons";
import { Pagination } from "../../common/Pagination";
import { SkillCard } from "../../skill/SkillCard";
import { Button, IconButton, EmptyState } from "../../common";
import { SkillFilterDropdown } from "../SkillFilterDropdown";
import type { SkillResponse } from "../../../types";

type EnabledFilter = "all" | "enabled" | "disabled";

const ENABLED_FILTER_OPTIONS: Array<{
  value: EnabledFilter;
  labelKey: string;
}> = [
  { value: "all", labelKey: "skills.filterAll" },
  { value: "enabled", labelKey: "skills.filterEnabled" },
  { value: "disabled", labelKey: "skills.filterDisabled" },
];

interface SkillsListProps {
  embedded?: boolean;
  searchQuery: string;
  setSearchQuery: (query: string) => void;
  selectedTags: string[];
  enabledFilter: "all" | "enabled" | "disabled";
  setEnabledFilter: (filter: "all" | "enabled" | "disabled") => void;
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
  canDelete: boolean;
  canPublish: boolean;
  selectedNames: Set<string>;
  onToggle: (name: string) => void;
  onTogglePreference: (
    skill: SkillResponse,
    preference: { is_favorite?: boolean; is_pinned?: boolean },
  ) => void;
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
  embedded = false,
  searchQuery,
  setSearchQuery,
  selectedTags,
  enabledFilter,
  setEnabledFilter,
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
  canDelete,
  canPublish,
  selectedNames,
  onToggle,
  onTogglePreference,
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

  const [filterOpen, setFilterOpen] = useState(false);

  const hasActiveFilters =
    searchQuery.trim().length > 0 ||
    selectedTags.length > 0 ||
    enabledFilter !== "all";
  const isInitialLoading =
    isLoading && filteredSkills.length === 0 && !hasActiveFilters;

  if (isInitialLoading) {
    return embedded ? <SkillsListSkeleton /> : <SkillsPanelSkeleton />;
  }

  const filterMenu = (
    <SkillFilterDropdown
      isOpen={filterOpen}
      label={t("skills.filter")}
      activeCount={(enabledFilter !== "all" ? 1 : 0) + selectedTags.length}
      options={ENABLED_FILTER_OPTIONS.map((opt) => ({
        value: opt.value,
        label: t(opt.labelKey),
      }))}
      value={enabledFilter}
      tags={availableTags}
      selectedTags={selectedTags}
      tagsLabel={t("adminMarketplace.tags")}
      clearLabel={t("marketplace.clearFilters")}
      onOpenChange={setFilterOpen}
      onValueChange={setEnabledFilter}
      onToggleTag={toggleTag}
      onClearFilters={clearFilters}
    />
  );

  const canSelect = canWrite || canDelete;
  const headerActions = (
    <div className="flex items-center gap-2">
      {canSelect && filteredSkills.length > 0 && (
        <Button variant="secondary" onClick={onSelectAll} className="h-10">
          <Check size={16} />
          <span className="hidden sm:inline">
            {selectedNames.size === filteredSkills.length &&
            filteredSkills.length > 0
              ? t("common.deselectAll")
              : t("common.selectAll")}
          </span>
        </Button>
      )}
      {canWrite && (
        <>
          <Button variant="secondary" onClick={onGithubClick} className="h-10">
            <Github size={16} />
            <span className="hidden sm:inline">{t("skills.github")}</span>
          </Button>
          <Button variant="secondary" onClick={onZipClick} className="h-10">
            <Archive size={16} />
            <span className="hidden sm:inline">{t("skills.uploadZip")}</span>
          </Button>
          <Button variant="primary" onClick={onCreate} className="h-10">
            <Plus size={16} />
            <span className="hidden sm:inline">{t("skills.newSkill")}</span>
          </Button>
        </>
      )}
    </div>
  );

  return (
    <div className="flex flex-1 min-h-0 flex-col overflow-y-auto">
      {embedded && (
        <PanelHeader
          className="skill-panel-header"
          title={t("skills.title")}
          searchOnly
          searchValue={searchQuery}
          onSearchChange={setSearchQuery}
          searchPlaceholder={t("skills.searchPlaceholder")}
          searchAccessory={filterMenu}
          searchActions={headerActions}
        />
      )}
      {!embedded && (
        <PanelHeader
          title={t("skills.title")}
          subtitle={t("skills.subtitle")}
          illustration="panel-skills"
          searchValue={searchQuery}
          onSearchChange={setSearchQuery}
          searchPlaceholder={t("skills.searchPlaceholder")}
          searchAccessory={filterMenu}
          actions={headerActions}
        />
      )}

      {/* Error */}
      {error && (
        <div className="mx-4 mt-4 flex items-center justify-between rounded-xl bg-red-50 p-3 text-14 text-red-700 dark:bg-red-900/30 dark:text-red-400">
          <span>{error}</span>
          <IconButton
            aria-label={t("common.close")}
            icon={<X size={18} />}
            onClick={clearError}
            className="hover:text-red-900 dark:hover:text-red-300"
          />
        </div>
      )}

      {/* Skills List */}
      <div className="panel-body skill-content-area flex-1 overflow-y-auto">
        {filteredSkills.length === 0 ? (
          <EmptyState
            icon={<FolderOpen size={28} />}
            title={
              hasActiveFilters
                ? t("skills.noMatchingSkills")
                : t("skills.noSkills")
            }
            description={
              hasActiveFilters
                ? t("skills.subtitle")
                : canWrite
                  ? t("skills.createFirst")
                  : undefined
            }
            action={
              !hasActiveFilters && canWrite ? (
                <Button variant="primary" onClick={onCreate}>
                  <Plus size={16} />
                  <span>{t("skills.newSkill")}</span>
                </Button>
              ) : hasActiveFilters ? (
                <Button
                  variant="secondary"
                  type="button"
                  onClick={clearFilters}
                >
                  {t("marketplace.clearFilters")}
                </Button>
              ) : undefined
            }
          />
        ) : (
          <div className="skill-grid grid auto-grid-cols gap-4">
            {paginatedSkills.map((skill) => (
              <SkillCard
                key={skill.name}
                skill={skill}
                onToggle={canWrite ? onToggle : undefined}
                onTogglePreference={onTogglePreference}
                onEdit={canWrite ? onEdit : undefined}
                onDelete={canDelete ? onDelete : undefined}
                onExportZip={onExportZip}
                onPublish={
                  canPublish ? (s: SkillResponse) => onPublish?.(s) : undefined
                }
                isPublished={skill.is_published}
                selected={canSelect && selectedNames.has(skill.name)}
                onSelect={canSelect ? onSelectSkill : undefined}
                selectionMode={canSelect}
              />
            ))}
          </div>
        )}
      </div>

      {/* Pagination */}
      <div className="panel-pagination empty:hidden">
        <Pagination
          page={page}
          pageSize={pageSize}
          total={total}
          onChange={setPage}
        />
      </div>
    </div>
  );
}
