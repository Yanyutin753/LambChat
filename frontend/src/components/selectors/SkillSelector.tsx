import { useState, useMemo } from "react";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import toast from "react-hot-toast";
import {
  Sparkles,
  ChevronRight,
  Plus,
  FileCode,
  Store,
  Search,
  Tag,
} from "lucide-react";
import { Checkbox } from "../common/Checkbox";

import type { SkillResponse, SkillSource } from "../../types";
import { collectSkillTags, skillMatchesQuery } from "../../utils/skillFilters";
import { useSwipeToClose } from "../../hooks/useSwipeToClose";
import { useBodyScrollLock } from "../../hooks/useBodyScrollLock";
import { useClientPagination } from "../../hooks/useClientPagination";
import { Pagination } from "../common/Pagination";
import { PanelSearchInput } from "../common/PanelSearchInput";
import {
  createPagedGroups,
  SelectorActionBar,
  SelectorActionButton,
  SelectorModalHeader,
  SelectorModalPortal,
  SelectorModalShell,
} from "./shared";

interface SkillSelectorProps {
  skills: SkillResponse[];
  onToggleSkill: (name: string) => Promise<boolean>;
  onToggleCategory: (
    category: SkillSource,
    enabled: boolean,
  ) => Promise<boolean>;
  onToggleAll: (enabled: boolean) => Promise<boolean>;
  pendingSkillNames?: string[];
  isMutating?: boolean;
  enabledCount: number;
  totalCount: number;
  controlledByPersonaName?: string | null;
  isOpen?: boolean;
  onOpenChange?: (open: boolean) => void;
  toastOnToggle?: boolean;
}

const sourceIcons: Record<SkillSource, typeof FileCode> = {
  marketplace: Store,
  manual: FileCode,
};

const sourceColors: Record<SkillSource, string> = {
  marketplace: "text-[var(--theme-primary)]",
  manual: "text-[var(--theme-text)]",
};

export function SkillSelector({
  skills,
  onToggleSkill,
  onToggleCategory,
  onToggleAll,
  pendingSkillNames = [],
  isMutating = false,
  enabledCount,
  totalCount,
  controlledByPersonaName,
  isOpen: externalIsOpen,
  onOpenChange: externalOnOpenChange,
  toastOnToggle = true,
}: SkillSelectorProps) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [internalOpen, setInternalOpen] = useState(false);
  const isOpen = externalIsOpen ?? internalOpen;
  const setIsOpen = externalOnOpenChange ?? setInternalOpen;
  const [expandedCategories, setExpandedCategories] = useState<
    Set<SkillSource>
  >(new Set(["marketplace", "manual"]));
  const [searchQuery, setSearchQuery] = useState("");
  const [selectedTags, setSelectedTags] = useState<string[]>([]);
  const swipeRef = useSwipeToClose({
    onClose: () => setIsOpen(false),
    enabled: isOpen,
  });

  useBodyScrollLock(isOpen);

  // 按来源分组 - 使用 useMemo 缓存计算结果
  const filteredSkills = useMemo(
    () =>
      skills.filter((skill) => {
        const matchesQuery = skillMatchesQuery(skill, searchQuery);
        const matchesTags =
          selectedTags.length === 0 ||
          selectedTags.every((tag) => skill.tags.includes(tag));

        return matchesQuery && matchesTags;
      }),
    [searchQuery, selectedTags, skills],
  );

  const { page, pageSize, setPage, totalPages } = useClientPagination({
    total: filteredSkills.length,
    resetKey: `${searchQuery}\u0000${selectedTags.join("\u0000")}`,
  });

  const { fullGroups: groupedSkills, pagedGroups: pagedGroupedSkills } =
    useMemo(
      () =>
        createPagedGroups(filteredSkills, {
          page,
          pageSize,
          getGroupKey: (skill) => skill.source,
        }),
      [filteredSkills, page, pageSize],
    );

  const availableTags = useMemo(() => collectSkillTags(skills), [skills]);
  const hasActiveFilters =
    searchQuery.trim().length > 0 || selectedTags.length > 0;
  const pendingSet = useMemo(
    () => new Set(pendingSkillNames),
    [pendingSkillNames],
  );
  const allSkillsEnabled = totalCount > 0 && enabledCount === totalCount;
  const noSkillsEnabled = enabledCount === 0;
  const personaControlled = !!controlledByPersonaName;

  const showBatchToggleToast = (
    enabled: boolean,
    count: number,
    ok: boolean,
  ) => {
    if (!toastOnToggle) return;
    if (ok) {
      toast.success(
        enabled
          ? t("skills.batchEnableSuccess", { count })
          : t("skills.batchDisableSuccess", { count }),
      );
      return;
    }
    toast.error(t("skills.batchToggleFailed"));
  };

  const showSingleToggleToast = (enabled: boolean, ok: boolean) => {
    if (!toastOnToggle) return;
    if (ok) {
      toast.success(
        enabled
          ? t("skills.batchEnableSuccess", { count: 1 })
          : t("skills.batchDisableSuccess", { count: 1 }),
      );
      return;
    }
    toast.error(t("skills.batchToggleFailed"));
  };

  const toggleCategoryExpand = (source: SkillSource) => {
    setExpandedCategories((prev) => {
      const newSet = new Set(prev);
      if (newSet.has(source)) {
        newSet.delete(source);
      } else {
        newSet.add(source);
      }
      return newSet;
    });
  };

  const toggleTag = (tag: string) => {
    setSelectedTags((prev) =>
      prev.includes(tag) ? prev.filter((item) => item !== tag) : [...prev, tag],
    );
  };

  const renderModalContent = () => (
    <SelectorModalShell ref={swipeRef as React.RefObject<HTMLDivElement>}>
      <SelectorModalHeader
        icon={
          <Sparkles
            size={16}
            className="text-stone-500 dark:text-amber-400 sm:w-[18px] sm:h-[18px]"
          />
        }
        title={t("skillSelector.title")}
        subtitle={t("skillSelector.selected", {
          enabled: enabledCount,
          total: totalCount,
        })}
        onClose={() => setIsOpen(false)}
      />

      {/* Actions */}
      <SelectorActionBar>
        <SelectorActionButton
          onClick={async () => {
            const changedCount = totalCount - enabledCount;
            if (changedCount === 0) {
              return;
            }
            const ok = await onToggleAll(true);
            showBatchToggleToast(true, changedCount, ok);
          }}
          disabled={personaControlled || isMutating || allSkillsEnabled}
          className="disabled:cursor-not-allowed disabled:opacity-50"
        >
          {t("skillSelector.selectAll")}
        </SelectorActionButton>
        <div className="w-px h-4 bg-stone-200 dark:bg-stone-700" />
        <SelectorActionButton
          onClick={async () => {
            if (enabledCount === 0) {
              return;
            }
            const ok = await onToggleAll(false);
            showBatchToggleToast(false, enabledCount, ok);
          }}
          disabled={personaControlled || isMutating || noSkillsEnabled}
          className="disabled:cursor-not-allowed disabled:opacity-50"
        >
          {t("skillSelector.deselectAll")}
        </SelectorActionButton>
        <div className="flex-1" />
        <SelectorActionButton
          accent
          onClick={() => {
            setIsOpen(false);
            navigate("/skills");
          }}
        >
          <Plus size={14} />
          <span>{t("skillSelector.manage")}</span>
        </SelectorActionButton>
      </SelectorActionBar>

      {personaControlled && (
        <div className="border-b border-blue-200/70 bg-blue-50/80 px-4 py-3 text-xs leading-relaxed text-blue-700 dark:border-blue-500/20 dark:bg-blue-500/10 dark:text-blue-200 sm:px-5">
          {t(
            "personaPresets.skillsControlledHint",
            'The current persona "{{name}}" is controlling available Skills. To adjust skills for this conversation, clear the current persona or edit the persona preset.',
            { name: controlledByPersonaName },
          )}
        </div>
      )}

      <div className="border-b border-stone-200/80 bg-stone-50/70 px-4 py-3 dark:border-stone-700/80 dark:bg-stone-900/40 sm:px-6">
        <div className="relative">
          <Search
            size={16}
            className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-stone-400 dark:text-stone-500"
          />
          <PanelSearchInput
            type="text"
            value={searchQuery}
            onValueChange={setSearchQuery}
            placeholder={t("skills.searchPlaceholder")}
            className="w-full rounded-2xl border border-stone-200 bg-white py-2.5 pl-9 pr-3 text-sm text-stone-700 shadow-sm outline-none transition-colors placeholder:text-stone-400 focus:border-[var(--theme-primary)] focus:bg-white dark:border-stone-700 dark:bg-stone-950/60 dark:text-stone-100 dark:placeholder:text-stone-500 dark:focus:bg-stone-950"
          />
        </div>
        {availableTags.length > 0 && (
          <div className="mt-3 flex flex-wrap gap-2">
            {availableTags.map((tag) => (
              <button
                key={tag}
                type="button"
                onClick={() => toggleTag(tag)}
                className={`skill-tag-chip ${
                  selectedTags.includes(tag) ? "skill-tag-chip--active" : ""
                }`}
              >
                <Tag size={11} />
                {tag}
              </button>
            ))}
            {hasActiveFilters && (
              <button
                type="button"
                onClick={() => {
                  setSearchQuery("");
                  setSelectedTags([]);
                }}
                className="text-xs text-[var(--theme-text-secondary)] transition-colors hover:text-[var(--theme-primary)]"
              >
                {t("marketplace.clearFilters")}
              </button>
            )}
          </div>
        )}
      </div>

      {/* Categories */}
      <div className="flex-1 overflow-y-auto bg-stone-50/60 p-3 sm:p-4 space-y-2 dark:bg-stone-950/20">
        {Object.entries(pagedGroupedSkills).map(
          ([source, pagedCategorySkills]: [string, SkillResponse[]]) => {
            const cat = source as SkillSource;
            const Icon = sourceIcons[cat];
            const allCategorySkills = groupedSkills[cat] || [];
            const enabledInCategory = allCategorySkills.filter(
              (s: SkillResponse) => s.enabled,
            ).length;
            const allEnabled = enabledInCategory === allCategorySkills.length;
            const isExpanded = expandedCategories.has(cat);
            const categoryPending = allCategorySkills.some((skill) =>
              pendingSet.has(skill.name),
            );
            const categoryTargetEnabled = !allEnabled;
            const categoryChangedCount = allCategorySkills.filter(
              (skill) => skill.enabled !== categoryTargetEnabled,
            ).length;

            return (
              <div
                key={source}
                className="rounded-2xl border border-stone-200/80 bg-white/90 shadow-sm shadow-stone-200/50 overflow-hidden dark:border-stone-700/70 dark:bg-stone-900/70 dark:shadow-black/10"
              >
                {/* Category Header */}
                <div
                  className="flex items-center gap-2 sm:gap-2.5 px-3.5 sm:px-4 py-3 cursor-pointer hover:bg-stone-50 dark:hover:bg-stone-800/70 active:bg-stone-100 dark:active:bg-stone-800 transition-all duration-200"
                  onClick={() => toggleCategoryExpand(cat)}
                >
                  <ChevronRight
                    size={16}
                    className={`text-stone-400 dark:text-stone-500 transition-transform duration-200 ease-out ${
                      isExpanded ? "rotate-90" : ""
                    }`}
                  />
                  <div className="w-7 h-7 sm:w-8 sm:h-8 rounded-xl bg-stone-50 dark:bg-stone-800 flex items-center justify-center shadow-sm border border-stone-100 dark:border-stone-700">
                    <Icon
                      size={13}
                      className={`${sourceColors[cat]} sm:w-[14px] sm:h-[14px]`}
                    />
                  </div>
                  <div className="flex-1 min-w-0">
                    <span className="text-[13px] sm:text-sm font-semibold text-stone-800 dark:text-stone-100">
                      {t(`skillSelector.sources.${cat}`)}
                    </span>
                    <span className="ml-1.5 sm:ml-2 text-xs sm:text-xs text-stone-400 dark:text-stone-500 tabular-nums">
                      {enabledInCategory}/{allCategorySkills.length}
                    </span>
                  </div>
                  <Checkbox
                    checked={allEnabled}
                    pending={categoryPending}
                    disabled={
                      personaControlled ||
                      isMutating ||
                      categoryChangedCount === 0
                    }
                    onChange={async () => {
                      if (
                        personaControlled ||
                        isMutating ||
                        categoryChangedCount === 0
                      )
                        return;
                      const ok = await onToggleCategory(
                        cat,
                        categoryTargetEnabled,
                      );
                      showBatchToggleToast(
                        categoryTargetEnabled,
                        categoryChangedCount,
                        ok,
                      );
                    }}
                  />
                </div>

                {/* Skills List */}
                {isExpanded && (
                  <div className="animate-[fade-in_150ms_ease-out]">
                    <div className="px-2 sm:px-3 pb-3 pt-1 space-y-1">
                      {pagedCategorySkills.map((skill: SkillResponse) => (
                        <div key={skill.name} className="group">
                          {/* Skill Row */}
                          <button
                            type="button"
                            disabled={personaControlled || isMutating}
                            className={`flex w-full items-center gap-1.5 sm:gap-2 px-2.5 sm:px-3 py-2.5 rounded-xl transition-all duration-200 disabled:cursor-not-allowed ${
                              skill.enabled
                                ? "hover:bg-stone-50 dark:hover:bg-stone-800/70 active:bg-stone-100/80 dark:active:bg-stone-800"
                                : "bg-[var(--theme-primary)]/[0.07] ring-1 ring-[var(--theme-primary)]/10 dark:bg-[var(--theme-primary)]/[0.10] hover:bg-[var(--theme-primary)]/[0.12] dark:hover:bg-[var(--theme-primary)]/[0.14] active:bg-[var(--theme-primary)]/[0.18] dark:active:bg-[var(--theme-primary)]/[0.20]"
                            } ${
                              pendingSet.has(skill.name) ||
                              personaControlled ||
                              isMutating
                                ? "opacity-70"
                                : ""
                            }`}
                            onClick={async () => {
                              if (personaControlled || isMutating) {
                                return;
                              }
                              const ok = await onToggleSkill(skill.name);
                              showSingleToggleToast(!skill.enabled, ok);
                            }}
                          >
                            <div className="flex-1 min-w-0">
                              <div className="flex items-center gap-1.5 sm:gap-2 flex-wrap">
                                <span
                                  className={`text-[12px] sm:text-[13px] font-medium truncate ${
                                    skill.enabled
                                      ? "text-stone-700 dark:text-stone-200"
                                      : "text-[var(--theme-primary)] dark:text-[var(--theme-primary)]"
                                  }`}
                                >
                                  {skill.name}
                                </span>
                              </div>
                              <p className="text-xs sm:text-xs text-stone-400 dark:text-stone-500 truncate mt-0.5 leading-relaxed text-left">
                                {skill.description ||
                                  t("skillSelector.noDescription")}
                              </p>
                            </div>
                            <Checkbox
                              checked={skill.enabled}
                              pending={pendingSet.has(skill.name)}
                              disabled={personaControlled || isMutating}
                              onChange={async () => {
                                if (personaControlled || isMutating) {
                                  return;
                                }
                                const ok = await onToggleSkill(skill.name);
                                showSingleToggleToast(!skill.enabled, ok);
                              }}
                            />
                          </button>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            );
          },
        )}
        {filteredSkills.length === 0 && (
          <div className="rounded-xl border border-dashed border-stone-200 bg-stone-50/70 px-4 py-6 text-center text-sm text-stone-500 dark:border-stone-700 dark:bg-stone-800/40 dark:text-stone-400">
            {t("skills.noMatchingSkills")}
          </div>
        )}
      </div>

      {totalPages > 1 && (
        <div className="px-4 sm:px-5 py-2 border-t border-stone-200/80 dark:border-stone-700/80 bg-stone-50/80 dark:bg-stone-800/50">
          <Pagination
            page={page}
            pageSize={pageSize}
            total={filteredSkills.length}
            onChange={setPage}
          />
        </div>
      )}
    </SelectorModalShell>
  );

  // When controlled externally, only render the modal — no trigger button
  if (externalOnOpenChange) {
    return (
      <SelectorModalPortal open={isOpen} onClose={() => setIsOpen(false)}>
        {renderModalContent()}
      </SelectorModalPortal>
    );
  }

  // 空状态：没有技能时显示禁用状态的图标（仅非外部控制模式）
  if (totalCount === 0) {
    return (
      <div className="relative" onClick={(e) => e.stopPropagation()}>
        <div
          className="flex items-center justify-center rounded-full p-2 border border-stone-200/50 dark:border-stone-700/50 bg-stone-50/50 dark:bg-stone-800/50 text-stone-300 dark:text-stone-600 cursor-not-allowed"
          title={t("skillSelector.noSkills")}
        >
          <Sparkles size={18} />
        </div>
      </div>
    );
  }

  return (
    <div className="relative" onClick={(e) => e.stopPropagation()}>
      {/* Trigger - ChatGPT style circular button */}
      <button
        type="button"
        onClick={(e) => {
          e.preventDefault();
          setIsOpen(true);
        }}
        className="chat-tool-btn"
        title={t("skillSelector.skillsEnabled", {
          enabled: enabledCount,
          total: totalCount,
          defaultValue: "{{enabled}}/{{total}} skills enabled",
        })}
      >
        <Sparkles size={18} />
      </button>

      {/* Modal */}
      {isOpen && (
        <SelectorModalPortal open={isOpen} onClose={() => setIsOpen(false)}>
          {renderModalContent()}
        </SelectorModalPortal>
      )}
    </div>
  );
}
