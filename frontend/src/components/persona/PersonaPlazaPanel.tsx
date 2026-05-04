import { useTranslation } from "react-i18next";
import {
  UserRound,
  Users,
  User,
  Plus,
  Sparkles,
  Tag,
  ChevronDown,
} from "lucide-react";
import { PanelHeader } from "../common/PanelHeader";
import { ConfirmDialog } from "../common/ConfirmDialog";
import { PersonaPlazaSkeleton } from "../skeletons";
import { usePersonaPlaza, type PersonaRouteState } from "./usePersonaPlaza";
import { PersonaPresetCard } from "./PersonaPresetCard";
import { PersonaEditorModal } from "./PersonaEditorModal";
import { PersonaScopeDropdown } from "./PersonaScopeDropdown";
import { PersonaTagFilterDropdown } from "./PersonaTagFilterDropdown";

export type { PersonaRouteState };

const SCOPE_ICON_MAP: Record<string, typeof Sparkles> = {
  Users,
  Sparkles,
  User,
};

export function PersonaPlazaPanel() {
  const { t } = useTranslation();

  const {
    isLoading,
    isMutating,
    canWrite,
    canAdmin,
    query,
    setQuery,
    activeTag,
    scopeFilter,
    selectedPresetId,
    filtered,
    allTags,
    scopeTabs,
    hasActiveFilters,
    clearFilters,
    toggleTag,
    handleScopeSelect,
    handleUse,
    handleClear,
    handleCopy,
    handleDelete,
    deleteTarget,
    setDeleteTarget,
    isDeleting,
    isScopeOpen,
    setIsScopeOpen,
    isFilterOpen,
    setIsFilterOpen,
    scopeBtnRef,
    tagBtnRef,
    showModal,
    closeModal,
    openModal,
    editingPreset,
    editorScope,
    createPreset,
    updatePreset,
  } = usePersonaPlaza();

  if (isLoading) return <PersonaPlazaSkeleton />;

  return (
    <div className="skill-theme-shell flex h-full min-h-0 flex-col">
      <PanelHeader
        className="skill-panel-header"
        title={t("personaPresets.title", "角色广场")}
        subtitle={t("personaPresets.subtitle", "选择一个角色开始对话")}
        icon={
          <UserRound size={18} className="text-stone-600 dark:text-stone-400" />
        }
        searchValue={query}
        onSearchChange={setQuery}
        searchPlaceholder={t("personaPresets.search", "搜索角色名称、描述...")}
        searchAccessory={
          <div className="flex items-center gap-2">
            <div className="shrink-0" data-scope-filter>
              <button
                ref={scopeBtnRef}
                type="button"
                onClick={() => {
                  setIsScopeOpen((prev) => !prev);
                  setIsFilterOpen(false);
                }}
                className={`btn-secondary h-10 px-2.5 ${
                  scopeFilter !== "all"
                    ? "border-[var(--theme-primary)] text-[var(--theme-text)]"
                    : ""
                }`}
              >
                {(() => {
                  const current = scopeTabs.find((s) => s.key === scopeFilter)!;
                  const CurrentIcon = SCOPE_ICON_MAP[current.icon] ?? Sparkles;
                  return (
                    <>
                      <CurrentIcon size={13} />
                      <span className="hidden sm:inline">{current.label}</span>
                    </>
                  );
                })()}
                <ChevronDown
                  size={13}
                  className={`transition-transform ${
                    isScopeOpen ? "rotate-180" : ""
                  }`}
                />
              </button>
            </div>
            {allTags.length > 0 && (
              <div className="shrink-0" data-persona-filter>
                <button
                  ref={tagBtnRef}
                  type="button"
                  onClick={() => {
                    setIsFilterOpen((prev) => !prev);
                    setIsScopeOpen(false);
                  }}
                  className={`btn-secondary h-10 px-2.5 ${
                    activeTag
                      ? "border-[var(--theme-primary)] text-[var(--theme-text)]"
                      : ""
                  }`}
                >
                  <Tag size={13} />
                  <span className="hidden sm:inline">
                    {t("personaPresets.tags", "标签")}
                  </span>
                  {activeTag && (
                    <span className="inline-flex h-4 min-w-4 items-center justify-center rounded-full bg-[var(--theme-primary-light)] px-1 text-[10px]">
                      1
                    </span>
                  )}
                  <ChevronDown
                    size={13}
                    className={`transition-transform ${
                      isFilterOpen ? "rotate-180" : ""
                    }`}
                  />
                </button>
              </div>
            )}
          </div>
        }
        actions={
          canWrite || canAdmin ? (
            <div className="flex items-center gap-2">
              {canWrite && (
                <button
                  onClick={() => openModal(null, "user")}
                  className="btn-secondary h-10"
                >
                  <Plus size={16} />
                  <span className="hidden sm:inline">
                    {t("personaPresets.createMine", "新建我的角色")}
                  </span>
                </button>
              )}
              {canAdmin && (
                <button
                  onClick={() => openModal(null, "global")}
                  className="btn-primary h-10"
                >
                  <Sparkles size={16} />
                  <span className="hidden sm:inline">
                    {t("personaPresets.publishOfficial", "发布官方角色")}
                  </span>
                </button>
              )}
            </div>
          ) : undefined
        }
      />

      <div className="skill-content-area flex-1 overflow-y-auto p-4 sm:p-6">
        {filtered.length === 0 ? (
          <div className="skill-empty-state">
            <div className="skill-empty-state__icon">
              <UserRound size={28} />
            </div>
            <p className="skill-empty-state__title">
              {query || activeTag
                ? t("personaPresets.noMatch", "没有匹配的角色")
                : t("personaPresets.empty", "暂无角色预设")}
            </p>
            <p className="skill-empty-state__description">
              {query || activeTag
                ? t("personaPresets.tryOtherFilters", "试试其他搜索条件")
                : t("personaPresets.emptyHint", "管理员可以创建官方角色预设")}
            </p>
            {hasActiveFilters && (
              <button onClick={clearFilters} className="btn-secondary mt-4">
                {t("personaPresets.clearFilters", "清除筛选")}
              </button>
            )}
          </div>
        ) : (
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 sm:gap-5 lg:grid-cols-3">
            {filtered.map((preset, index) => (
              <div
                key={preset.id}
                style={{ animationDelay: `${index * 60}ms` }}
              >
                <PersonaPresetCard
                  preset={preset}
                  selected={selectedPresetId === preset.id}
                  activeTag={activeTag}
                  canWrite={canWrite}
                  canAdmin={canAdmin}
                  onUse={handleUse}
                  onClear={handleClear}
                  onCopy={handleCopy}
                  onEdit={(p) => openModal(p)}
                  onDelete={(p) => setDeleteTarget(p)}
                  onToggleTag={toggleTag}
                />
              </div>
            ))}
          </div>
        )}
      </div>

      <PersonaEditorModal
        showModal={showModal}
        editingPreset={editingPreset}
        editorScope={editorScope}
        canAdmin={canAdmin}
        isMutating={isMutating}
        createPreset={createPreset}
        updatePreset={updatePreset}
        onClose={closeModal}
      />

      <ConfirmDialog
        isOpen={!!deleteTarget}
        title={t("personaPresets.confirmDelete", "删除角色")}
        message={
          deleteTarget
            ? t(
                "personaPresets.confirmDeleteMessage",
                "确定要删除角色「{{name}}」吗？此操作不可撤销。",
                { name: deleteTarget.name },
              )
            : ""
        }
        confirmText={t("common.delete", "删除")}
        cancelText={t("common.cancel", "取消")}
        variant="danger"
        loading={isDeleting}
        onConfirm={handleDelete}
        onCancel={() => setDeleteTarget(null)}
      />

      <PersonaScopeDropdown
        isOpen={isScopeOpen}
        scopeFilter={scopeFilter}
        scopeTabs={scopeTabs}
        scopeBtnRef={scopeBtnRef}
        onSelect={handleScopeSelect}
        onClose={() => setIsScopeOpen(false)}
      />

      <PersonaTagFilterDropdown
        isOpen={isFilterOpen}
        allTags={allTags}
        activeTag={activeTag}
        hasActiveFilters={hasActiveFilters}
        tagBtnRef={tagBtnRef}
        onToggleTag={toggleTag}
        onClearFilters={clearFilters}
        onClose={() => setIsFilterOpen(false)}
      />
    </div>
  );
}

export default PersonaPlazaPanel;
