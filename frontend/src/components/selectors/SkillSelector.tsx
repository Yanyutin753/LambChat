import { useState, useEffect, useMemo } from "react";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import {
  Sparkles,
  ChevronRight,
  Check,
  X,
  Plus,
  Github,
  FileCode,
  Settings,
} from "lucide-react";
import type { SkillResponse, SkillSource } from "../../types";

interface SkillSelectorProps {
  skills: SkillResponse[];
  onToggleSkill: (name: string) => Promise<void>;
  onToggleCategory: (category: SkillSource, enabled: boolean) => Promise<void>;
  onToggleAll: (enabled: boolean) => Promise<void>;
  enabledCount: number;
  totalCount: number;
}

const sourceIcons: Record<SkillSource, typeof FileCode> = {
  builtin: Settings,
  github: Github,
  manual: FileCode,
};

const sourceColors: Record<SkillSource, string> = {
  builtin: "text-stone-500 dark:text-amber-400",
  github: "text-gray-600 dark:text-gray-400",
  manual: "text-blue-600 dark:text-blue-400",
};

export function SkillSelector({
  skills,
  onToggleSkill,
  onToggleCategory,
  onToggleAll,
  enabledCount,
  totalCount,
}: SkillSelectorProps) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [isOpen, setIsOpen] = useState(false);
  const [expandedCategories, setExpandedCategories] = useState<
    Set<SkillSource>
  >(new Set(["builtin", "github", "manual"]));

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
  const groupedSkills = useMemo(
    () =>
      skills.reduce(
        (acc, skill) => {
          if (!acc[skill.source]) {
            acc[skill.source] = [];
          }
          acc[skill.source].push(skill);
          return acc;
        },
        {} as Record<SkillSource, SkillResponse[]>,
      ),
    [skills],
  );

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

  const ModalContent = () => (
    <div className="bg-white dark:bg-stone-800 sm:rounded-2xl rounded-t-2xl shadow-2xl w-full sm:w-[480px] sm:max-h-[80vh] max-h-[85vh] flex flex-col overflow-hidden">
      {/* Header */}
      <div className="flex items-center justify-between px-4 sm:px-5 py-3 sm:py-4 border-b border-stone-200 dark:border-stone-700">
        {/* Mobile drag handle */}
        <div className="absolute left-1/2 -translate-x-1/2 top-2 w-10 h-1 rounded-full bg-stone-300 dark:bg-stone-600 sm:hidden" />
        <div className="flex items-center gap-3 mt-2 sm:mt-0">
          <div className="w-8 h-8 sm:w-9 sm:h-9 rounded-xl bg-gradient-to-br from-stone-100 to-stone-200 dark:from-amber-500/20 dark:to-orange-500/20 flex items-center justify-center">
            <Sparkles
              size={16}
              className="text-stone-500 dark:text-amber-400 sm:w-[18px] sm:h-[18px]"
            />
          </div>
          <div>
            <h2 className="text-sm sm:text-base font-semibold text-stone-900 dark:text-stone-100">
              {t("skillSelector.title")}
            </h2>
            <p className="text-[11px] sm:text-xs text-stone-500 dark:text-stone-400">
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
          onClick={() => onToggleAll(true)}
          className="px-3 py-2 sm:py-1.5 text-xs font-medium text-stone-600 dark:text-stone-300 hover:text-stone-900 dark:hover:text-stone-100 hover:bg-stone-100 dark:hover:bg-stone-700 active:bg-stone-200 dark:active:bg-stone-600 rounded-lg transition-colors"
        >
          {t("skillSelector.selectAll")}
        </button>
        <div className="w-px h-4 bg-stone-200 dark:bg-stone-700" />
        <button
          onClick={() => onToggleAll(false)}
          className="px-3 py-2 sm:py-1.5 text-xs font-medium text-stone-600 dark:text-stone-300 hover:text-stone-900 dark:hover:text-stone-100 hover:bg-stone-100 dark:hover:bg-stone-700 active:bg-stone-200 dark:active:bg-stone-600 rounded-lg transition-colors"
        >
          {t("skillSelector.deselectAll")}
        </button>
        <div className="flex-1" />
        <button
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
                    <span className="ml-1.5 sm:ml-2 text-[11px] sm:text-xs text-stone-400 dark:text-stone-500 tabular-nums">
                      {enabledInCategory}/{categorySkills.length}
                    </span>
                  </div>
                  <button
                    onClick={async (e) => {
                      e.stopPropagation();
                      await onToggleCategory(cat, !allEnabled);
                    }}
                    className={`w-5 h-5 sm:w-5 sm:h-5 rounded border-2 flex items-center justify-center transition-all duration-200 flex-shrink-0 ${
                      allEnabled
                        ? "bg-stone-500 dark:bg-amber-400 border-stone-500 dark:border-amber-400"
                        : "border-stone-300 dark:border-stone-600 hover:border-stone-400 dark:hover:border-stone-500"
                    }`}
                  >
                    {allEnabled && (
                      <Check
                        size={12}
                        className="text-white dark:text-stone-900"
                      />
                    )}
                  </button>
                </div>

                {/* Skills List */}
                <div
                  className={`grid transition-all duration-300 ease-out ${
                    isExpanded
                      ? "grid-rows-[1fr] opacity-100"
                      : "grid-rows-[0fr] opacity-0"
                  }`}
                >
                  <div className="overflow-hidden">
                    <div className="px-1.5 sm:px-2 pb-2 pt-1 space-y-0.5">
                      {categorySkills.map((skill: SkillResponse) => (
                        <div key={skill.name} className="group">
                          {/* Skill Row */}
                          <div
                            className="flex items-center gap-1.5 sm:gap-2 px-2 sm:px-2.5 py-2 sm:py-2 rounded-lg hover:bg-white dark:hover:bg-stone-700/50 active:bg-stone-100 dark:active:bg-stone-600/50 cursor-pointer transition-all duration-150"
                            onClick={async () =>
                              await onToggleSkill(skill.name)
                            }
                          >
                            <div className="flex-1 min-w-0">
                              <div className="flex items-center gap-1.5 sm:gap-2 flex-wrap">
                                <span className="text-[12px] sm:text-[13px] font-medium text-stone-700 dark:text-stone-200 truncate">
                                  {skill.name}
                                </span>
                                {skill.is_system && (
                                  <span className="text-[9px] sm:text-[10px] px-1.5 py-0.5 rounded-md bg-stone-100 dark:bg-amber-500/20 text-stone-500 dark:text-amber-400 font-medium">
                                    {t("skillSelector.system")}
                                  </span>
                                )}
                              </div>
                              <p className="text-[10px] sm:text-[11px] text-stone-400 dark:text-stone-500 truncate mt-0.5 leading-relaxed">
                                {skill.description ||
                                  t("skillSelector.noDescription")}
                              </p>
                            </div>
                            <div
                              className={`w-5 h-5 rounded border-2 flex items-center justify-center transition-all duration-200 flex-shrink-0 ${
                                skill.enabled
                                  ? "bg-stone-500 dark:bg-amber-400 border-stone-500 dark:border-amber-400"
                                  : "border-stone-300 dark:border-stone-600 group-hover:border-stone-400 dark:group-hover:border-stone-500"
                              }`}
                            >
                              {skill.enabled && (
                                <Check
                                  size={12}
                                  className="text-white dark:text-stone-900"
                                />
                              )}
                            </div>
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                </div>
              </div>
            );
          },
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
          className="flex items-center justify-center rounded-full p-2 border border-gray-200/50 dark:border-stone-700/50 bg-gray-50/50 dark:bg-stone-800/50 text-gray-300 dark:text-stone-600 cursor-not-allowed"
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
        onClick={() => setIsOpen(true)}
        className="flex items-center justify-center rounded-full p-2 border border-gray-200 dark:border-stone-700 bg-transparent hover:bg-gray-100 dark:hover:bg-stone-700 text-stone-500 dark:text-stone-300 dark:hover:bg-stone-800 dark:hover:text-amber-300 transition-all duration-300"
        title={`${enabledCount}/${totalCount} ${t(
          "skillSelector.skillsEnabled",
        )}`}
      >
        <Sparkles size={18} />
      </button>

      {/* Modal */}
      {isOpen && (
        <>
          {/* Backdrop - hidden on mobile */}
          <div
            className="hidden sm:block fixed inset-0 z-50 bg-black/50 animate-fade-in"
            onClick={() => setIsOpen(false)}
          />

          {/* Mobile backdrop - darker */}
          <div
            className="sm:hidden fixed inset-0 z-50 bg-black/60 animate-fade-in"
            onClick={() => setIsOpen(false)}
          />

          {/* Modal Content - Desktop: centered, Mobile: bottom sheet */}
          <div className="fixed z-50 sm:inset-0 sm:flex sm:items-center sm:justify-center sm:p-4 inset-x-0 bottom-0 animate-slide-up sm:animate-scale-in">
            <ModalContent />
          </div>
        </>
      )}
    </div>
  );
}
