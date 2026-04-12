import { useState, useEffect, useMemo } from "react";
import { createPortal } from "react-dom";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import toast from "react-hot-toast";
import {
  Sparkles,
  ChevronRight,
  X,
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
}: SkillSelectorProps) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [isOpen, setIsOpen] = useState(false);
  const [expandedCategories, setExpandedCategories] = useState<
    Set<SkillSource>
  >(new Set(["marketplace", "manual"]));
  const [searchQuery, setSearchQuery] = useState("");
  const [selectedTags, setSelectedTags] = useState<string[]>([]);
  const swipeRef = useSwipeToClose({
    onClose: () => setIsOpen(false),
    enabled: isOpen,
  });

  // 锁定滚动
  useEffect(() => {
    if (isOpen) {
      document.body.style.overflow = "hidden";
    } else {
      document.body.style.overflow = "";
    }
    return () => {
      document.body.style.overflow = "";
    };
  }, [isOpen]);

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

  const groupedSkills = useMemo(
    () =>
      filteredSkills.reduce(
        (acc, skill) => {
          if (!acc[skill.source]) {
            acc[skill.source] = [];
          }
          acc[skill.source].push(skill);
          return acc;
        },
        {} as Record<SkillSource, SkillResponse[]>,
      ),
    [filteredSkills],
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

  const showBatchToggleToast = (
    enabled: boolean,
    count: number,
    ok: boolean,
  ) => {
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

  const ModalContent = () => (
    <div
      ref={swipeRef as React.RefObject<HTMLDivElement>}
      className="sm:rounded-2xl rounded-t-2xl shadow-2xl w-full sm:w-[40%] sm:min-w-[600px] min-h-[40vh] sm:max-h-[80vh] max-h-[85vh] max-h-[85dvh] flex flex-col overflow-hidden"
      style={{ background: "var(--theme-bg-card)" }}
      onClick={(e) => e.stopPropagation()}
    >
      {/* Header */}
      <div
        className="flex items-center justify-between px-4 sm:px-5 py-3 sm:py-4 border-b"
        style={{ borderColor: "var(--theme-border)" }}
      >
        {/* Mobile drag handle */}
        <div className="absolute left-1/2 -translate-x-1/2 top-2 w-10 h-1 rounded-full bg-stone-300 dark:bg-stone-600 sm:hidden" />
        <div className="flex items-center gap-3 mt-2 sm:mt-0">
          <div className="size-9 sm:size-10 rounded-xl bg-gradient-to-br from-stone-100 to-stone-200 dark:from-amber-500/20 dark:to-orange-500/20 flex items-center justify-center">
            <Sparkles
              size={16}
              className="text-stone-500 dark:text-amber-400 sm:w-[18px] sm:h-[18px]"
            />
          </div>
          <div>
            <h2 className="text-sm sm:text-base font-semibold text-stone-900 dark:text-stone-100 font-serif">
              {t("skillSelector.title")}
            </h2>
            <p className="text-xs sm:text-xs text-stone-500 dark:text-stone-400">
              {t("skillSelector.selected", {
                enabled: enabledCount,
                total: totalCount,
              })}
            </p>
          </div>
        </div>
        <button
          onClick={() => setIsOpen(false)}
          className="p-2 rounded-lg hover:bg-stone-100 dark:hover:bg-stone-700 active:bg-stone-200 dark:active:bg-stone-600 transition-colors"
        >
          <X size={18} className="text-stone-400 dark:text-stone-500" />
        </button>
      </div>

      {/* Actions */}
      <div className="flex items-center gap-2 px-4 sm:px-5 py-2 sm:py-2.5 border-b border-stone-200/80 dark:border-stone-700/80 bg-stone-50/80 dark:bg-stone-800/50">
        <button
          onClick={async () => {
            const changedCount = totalCount - enabledCount;
            if (changedCount === 0) {
              return;
            }
            const ok = await onToggleAll(true);
            showBatchToggleToast(true, changedCount, ok);
          }}
          disabled={isMutating || allSkillsEnabled}
          className="px-3 py-2 sm:py-1.5 text-xs font-medium text-stone-600 dark:text-stone-300 hover:text-stone-900 dark:hover:text-stone-100 hover:bg-stone-100 dark:hover:bg-stone-700 active:bg-stone-200 dark:active:bg-stone-600 rounded-lg transition-colors disabled:cursor-not-allowed disabled:opacity-50"
        >
          {t("skillSelector.selectAll")}
        </button>
        <div className="w-px h-4 bg-stone-200 dark:bg-stone-700" />
        <button
          onClick={async () => {
            if (enabledCount === 0) {
              return;
            }
            const ok = await onToggleAll(false);
            showBatchToggleToast(false, enabledCount, ok);
          }}
          disabled={isMutating || noSkillsEnabled}
          className="px-3 py-2 sm:py-1.5 text-xs font-medium text-stone-600 dark:text-stone-300 hover:text-stone-900 dark:hover:text-stone-100 hover:bg-stone-100 dark:hover:bg-stone-700 active:bg-stone-200 dark:active:bg-stone-600 rounded-lg transition-colors disabled:cursor-not-allowed disabled:opacity-50"
        >
          {t("skillSelector.deselectAll")}
        </button>
        <div className="flex-1" />
        <button
          type="button"
          onClick={() => {
            setIsOpen(false);
            navigate("/skills");
          }}
          className="flex items-center gap-1 px-3 py-2 sm:py-1.5 text-xs font-medium text-stone-500 dark:text-amber-400 hover:text-stone-700 dark:hover:text-amber-300 hover:bg-stone-100 dark:hover:bg-amber-500/10 active:bg-stone-200 dark:active:bg-amber-500/20 rounded-lg transition-colors"
        >
          <Plus size={14} />
          <span>{t("skillSelector.manage")}</span>
        </button>
      </div>

      <div className="border-b border-stone-200/80 bg-white/80 px-4 py-3 dark:border-stone-700/80 dark:bg-stone-800/60 sm:px-5">
        <div className="relative">
          <Search
            size={16}
            className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-stone-400 dark:text-stone-500"
          />
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder={t("skills.searchPlaceholder")}
            className="w-full rounded-xl border border-stone-200 bg-stone-50 py-2 pl-9 pr-3 text-sm text-stone-700 outline-none transition-colors focus:border-[var(--theme-primary)] focus:bg-white dark:border-stone-700 dark:bg-stone-900/60 dark:text-stone-100 dark:focus:bg-stone-900"
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
      <div className="flex-1 overflow-y-auto p-2.5 sm:p-3 space-y-1.5">
        {Object.entries(groupedSkills).map(
          ([source, categorySkills]: [string, SkillResponse[]]) => {
            const cat = source as SkillSource;
            const Icon = sourceIcons[cat];
            const enabledInCategory = categorySkills.filter(
              (s: SkillResponse) => s.enabled,
            ).length;
            const allEnabled = enabledInCategory === categorySkills.length;
            const isExpanded = expandedCategories.has(cat);
            const categoryPending = categorySkills.some((skill) =>
              pendingSet.has(skill.name),
            );
            const categoryTargetEnabled = !allEnabled;
            const categoryChangedCount = categorySkills.filter(
              (skill) => skill.enabled !== categoryTargetEnabled,
            ).length;

            return (
              <div
                key={source}
                className="rounded-xl border border-stone-200/80 dark:border-stone-700/60 overflow-hidden bg-stone-50/50 dark:bg-stone-800/40"
              >
                {/* Category Header */}
                <div
                  className="flex items-center gap-2 sm:gap-2.5 px-3 sm:px-3.5 py-2.5 cursor-pointer hover:bg-stone-100/60 dark:hover:bg-stone-700/40 active:bg-stone-100 dark:active:bg-stone-700/50 transition-all duration-200"
                  onClick={() => toggleCategoryExpand(cat)}
                >
                  <ChevronRight
                    size={16}
                    className={`text-stone-400 dark:text-stone-500 transition-transform duration-200 ease-out ${
                      isExpanded ? "rotate-90" : ""
                    }`}
                  />
                  <div className="w-6 h-6 sm:w-7 sm:h-7 rounded-lg bg-white dark:bg-stone-700 flex items-center justify-center shadow-sm border border-stone-100 dark:border-stone-600">
                    <Icon
                      size={13}
                      className={`${sourceColors[cat]} sm:w-[14px] sm:h-[14px]`}
                    />
                  </div>
                  <div className="flex-1 min-w-0">
                    <span className="text-[13px] sm:text-sm font-medium text-stone-700 dark:text-stone-200">
                      {t(`skillSelector.sources.${cat}`)}
                    </span>
                    <span className="ml-1.5 sm:ml-2 text-xs sm:text-xs text-stone-400 dark:text-stone-500 tabular-nums">
                      {enabledInCategory}/{categorySkills.length}
                    </span>
                  </div>
                  <Checkbox
                    checked={allEnabled}
                    pending={categoryPending}
                    disabled={isMutating || categoryChangedCount === 0}
                    onChange={async () => {
                      if (isMutating || categoryChangedCount === 0) return;
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
                    <div className="px-1 sm:px-2 pb-2 pt-1 space-y-0.5">
                      {categorySkills.map((skill: SkillResponse) => (
                        <div key={skill.name} className="group">
                          {/* Skill Row */}
                          <button
                            type="button"
                            disabled={isMutating}
                            className={`flex w-full items-center gap-1.5 sm:gap-2 px-2 sm:px-2.5 py-2 sm:py-2 rounded-lg transition-all duration-200 disabled:cursor-not-allowed ${
                              skill.enabled
                                ? "hover:bg-stone-50 dark:hover:bg-stone-700/30 active:bg-stone-100/80 dark:active:bg-stone-600/40"
                                : "bg-[var(--theme-primary)]/[0.06] dark:bg-[var(--theme-primary)]/[0.08] hover:bg-[var(--theme-primary)]/[0.12] dark:hover:bg-[var(--theme-primary)]/[0.14] active:bg-[var(--theme-primary)]/[0.18] dark:active:bg-[var(--theme-primary)]/[0.20]"
                            } ${
                              pendingSet.has(skill.name) || isMutating
                                ? "opacity-70"
                                : ""
                            }`}
                            onClick={async () => {
                              if (isMutating) {
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
                              onChange={async () => {
                                if (isMutating) {
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

      {/* Footer */}
      <div className="px-4 sm:px-5 py-3 sm:py-3.5 border-t border-stone-200 dark:border-stone-700 bg-stone-50/80 dark:bg-stone-800/50 pb-[max(0.75rem,env(safe-area-inset-bottom))]">
        <button
          onClick={() => setIsOpen(false)}
          className="w-full py-2.5 px-4 bg-stone-900 dark:bg-stone-600 text-white dark:text-stone-100 rounded-xl font-medium text-sm hover:bg-stone-800 dark:hover:bg-stone-500 active:bg-stone-700 dark:active:bg-stone-600 transition-colors"
        >
          {t("skillSelector.done")}
        </button>
      </div>
    </div>
  );

  // 空状态：没有技能时显示禁用状态的图标
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
        title={`${enabledCount}/${totalCount} ${t(
          "skillSelector.skillsEnabled",
        )}`}
      >
        <Sparkles size={18} />
      </button>

      {/* Modal */}
      {isOpen &&
        createPortal(
          <>
            <div
              className="fixed inset-0 z-[300] bg-black/50 animate-fade-in"
              onClick={() => setIsOpen(false)}
            />

            {/* Modal Content - Desktop: centered, Mobile: bottom sheet */}
            <div
              className="fixed z-[301] sm:inset-0 sm:flex sm:items-center sm:justify-center sm:p-4 inset-x-0 bottom-0 animate-slide-up sm:animate-scale-in"
              onClick={() => setIsOpen(false)}
            >
              <ModalContent />
            </div>
          </>,
          document.body,
        )}
    </div>
  );
}
