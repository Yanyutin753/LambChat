import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  X,
  Sparkles,
  ChevronDown,
  Check,
  Plus,
  Search,
  Loader2,
} from "lucide-react";
import { useSkills } from "../../hooks/useSkills";
import { PanelSearchInput } from "../common/PanelSearchInput";
import { PERSONA_SKILL_PAGE_SIZE } from "./PersonaEditorTypes";

interface SkillSelectorProps {
  skillNames: string[];
  onSkillNamesChange: (updater: (prev: string[]) => string[]) => void;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function SkillSelector({
  skillNames,
  onSkillNamesChange,
  open,
  onOpenChange,
}: SkillSelectorProps) {
  const { t } = useTranslation();
  const [skillSearch, setSkillSearch] = useState("");
  const [skillPage, setSkillPage] = useState(1);
  const [skillActiveIndex, setSkillActiveIndex] = useState(-1);
  const skillDropdownRef = useRef<HTMLDivElement>(null);
  const skillItemRefs = useRef<Map<number, HTMLButtonElement>>(new Map());
  const skillSearchInputRef = useRef<HTMLInputElement>(null);

  const handleSkillSearchChange = useCallback((query: string) => {
    setSkillPage(1);
    setSkillSearch(query);
  }, []);

  const skillListParams = useMemo(
    () => ({
      skip: (skillPage - 1) * PERSONA_SKILL_PAGE_SIZE,
      limit: PERSONA_SKILL_PAGE_SIZE,
      q: skillSearch.trim() || undefined,
    }),
    [skillPage, skillSearch],
  );

  const {
    skills: allSkills,
    total: totalSkills,
    isLoading: skillsLoading,
  } = useSkills({
    enabled: open,
    listParams: skillListParams,
    appendPages: true,
  });

  const hasMoreSkills = allSkills.length < totalSkills;

  const handleSkillListScroll = useCallback(
    (event: React.UIEvent<HTMLDivElement>) => {
      if (skillsLoading || !hasMoreSkills) {
        return;
      }
      const target = event.currentTarget;
      const distanceToBottom =
        target.scrollHeight - target.scrollTop - target.clientHeight;
      if (distanceToBottom <= 48) {
        setSkillPage((page) => page + 1);
      }
    },
    [hasMoreSkills, skillsLoading],
  );

  const displayedSkills = useMemo(() => {
    return [...allSkills].sort((a, b) => {
      const aSel = skillNames.includes(a.name) ? 0 : 1;
      const bSel = skillNames.includes(b.name) ? 0 : 1;
      return aSel - bSel;
    });
  }, [allSkills, skillNames]);

  // Reset active index when search query changes
  useEffect(() => {
    setSkillActiveIndex(-1);
    skillItemRefs.current.clear();
  }, [skillSearch]);

  // Clamp active index when list length changes (e.g. pagination)
  useEffect(() => {
    setSkillActiveIndex((prev) => {
      if (prev >= displayedSkills.length) return -1;
      return prev;
    });
  }, [displayedSkills.length]);

  // Close on outside click
  useEffect(() => {
    const handleClick = (e: MouseEvent) => {
      const target = e.target as HTMLElement;
      if (
        open &&
        skillDropdownRef.current &&
        !skillDropdownRef.current.contains(target)
      ) {
        onOpenChange(false);
      }
    };
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, [open, onOpenChange]);

  // Keyboard navigation for skill dropdown
  useEffect(() => {
    if (!open) return;

    const handleKeyDown = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement;
      if (!skillDropdownRef.current?.contains(target)) return;

      if (e.key === "Escape") {
        e.preventDefault();
        onOpenChange(false);
        skillSearchInputRef.current?.blur();
        return;
      }

      if (e.key === "ArrowDown") {
        e.preventDefault();
        setSkillActiveIndex((prev) => {
          if (displayedSkills.length === 0) return -1;
          const next = prev < displayedSkills.length - 1 ? prev + 1 : 0;
          skillItemRefs.current.get(next)?.scrollIntoView({ block: "nearest" });
          return next;
        });
        return;
      }

      if (e.key === "ArrowUp") {
        e.preventDefault();
        setSkillActiveIndex((prev) => {
          if (prev <= 0) {
            skillSearchInputRef.current?.focus();
            return -1;
          }
          const next = prev - 1;
          skillItemRefs.current.get(next)?.scrollIntoView({ block: "nearest" });
          return next;
        });
        return;
      }

      if (e.key === "Enter" || e.key === " ") {
        if (target === skillSearchInputRef.current) return;
        e.preventDefault();
        if (
          skillActiveIndex >= 0 &&
          skillActiveIndex < displayedSkills.length
        ) {
          const skill = displayedSkills[skillActiveIndex];
          const isSelected = skillNames.includes(skill.name);
          onSkillNamesChange((prev) =>
            isSelected
              ? prev.filter((n) => n !== skill.name)
              : [...prev, skill.name],
          );
        }
        return;
      }
    };

    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [
    skillActiveIndex,
    open,
    displayedSkills,
    skillNames,
    onSkillNamesChange,
    onOpenChange,
  ]);

  const toggleSkill = useCallback(
    (name: string) => {
      onSkillNamesChange((prev) =>
        prev.includes(name) ? prev.filter((n) => n !== name) : [...prev, name],
      );
    },
    [onSkillNamesChange],
  );

  const removeSkill = useCallback(
    (name: string) => {
      onSkillNamesChange((prev) => prev.filter((n) => n !== name));
    },
    [onSkillNamesChange],
  );

  return (
    <div ref={skillDropdownRef} className="relative">
      <button
        type="button"
        onClick={() => {
          if (open) {
            onOpenChange(false);
          } else {
            onOpenChange(true);
            setSkillSearch("");
            setSkillPage(1);
            setSkillActiveIndex(-1);
            skillItemRefs.current.clear();
          }
        }}
        aria-haspopup="listbox"
        aria-expanded={open}
        className={`ppe-skill-trigger ${open ? "ppe-skill-trigger--open" : ""}`}
      >
        {skillNames.length > 0 ? (
          <span className="ppe-skill-trigger__count">
            <Sparkles size={12} />
            {t("personaPresets.skillCount", "{{count}} 个技能已选择", {
              count: skillNames.length,
            })}
          </span>
        ) : (
          <span className="ppe-skill-trigger__placeholder">
            {t("personaPresets.skillsInputPlaceholder", "选择技能...")}
          </span>
        )}
        <ChevronDown
          size={14}
          className={`ppe-skill-trigger__chevron ${open ? "rotate-180" : ""}`}
        />
      </button>

      {skillNames.length > 0 && !open && (
        <div className="ppe-skill-selected-area">
          {skillNames.map((name) => (
            <span key={name} className="ppe-skill-chip">
              {name}
              <X
                size={11}
                className="ppe-skill-chip-remove"
                onClick={() => removeSkill(name)}
              />
            </span>
          ))}
        </div>
      )}

      {open && (
        <div className="ppe-skill-dropdown">
          <div className="ppe-skill-dropdown__header">
            <div className="ppe-skill-dropdown__search-wrap">
              <Search size={14} className="ppe-skill-dropdown__search-icon" />
              <PanelSearchInput
                ref={skillSearchInputRef}
                type="text"
                value={skillSearch}
                onValueChange={handleSkillSearchChange}
                placeholder={t("skills.searchPlaceholder", "搜索技能...")}
                className="ppe-skill-search"
                autoFocus
                role="combobox"
                aria-expanded={open}
                aria-controls="ppe-skill-listbox"
                aria-activedescendant={
                  skillActiveIndex >= 0 &&
                  skillActiveIndex < displayedSkills.length
                    ? `ppe-skill-option-${skillActiveIndex}`
                    : undefined
                }
                aria-label={t("skills.searchSkills", "搜索技能")}
              />
            </div>
            {skillNames.length > 0 && (
              <button
                type="button"
                className="ppe-skill-dropdown__clear-all"
                onClick={() => onSkillNamesChange(() => [])}
              >
                {t("common.clearAll", "清除全部")}
              </button>
            )}
          </div>

          {skillNames.length > 0 && (
            <div className="ppe-skill-selected-bar">
              {skillNames.map((name) => (
                <span key={name} className="ppe-skill-chip">
                  {name}
                  <X
                    size={11}
                    className="ppe-skill-chip-remove"
                    onClick={() => removeSkill(name)}
                  />
                </span>
              ))}
            </div>
          )}

          <div
            className="ppe-skill-dropdown__list"
            onScroll={handleSkillListScroll}
            role="listbox"
            id="ppe-skill-listbox"
            aria-label={t("skills.skillList", "技能列表")}
          >
            {displayedSkills.length > 0 ? (
              displayedSkills.map((skill, index) => {
                const isSelected = skillNames.includes(skill.name);
                return (
                  <button
                    key={skill.name}
                    type="button"
                    ref={(el) => {
                      if (el) {
                        skillItemRefs.current.set(index, el);
                      } else {
                        skillItemRefs.current.delete(index);
                      }
                    }}
                    onClick={() => toggleSkill(skill.name)}
                    onMouseEnter={() => setSkillActiveIndex(index)}
                    className={`ppe-skill-option ${
                      isSelected ? "ppe-skill-option--selected" : ""
                    } ${
                      index === skillActiveIndex
                        ? "ppe-skill-option--active"
                        : ""
                    }`}
                    role="option"
                    aria-selected={isSelected}
                    id={`ppe-skill-option-${index}`}
                  >
                    <div className="ppe-skill-option__check-ring">
                      {isSelected ? (
                        <Check
                          size={12}
                          className="ppe-skill-option__check-icon"
                        />
                      ) : (
                        <Plus
                          size={12}
                          className="ppe-skill-option__plus-icon"
                        />
                      )}
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="text-sm font-medium truncate">
                        {skill.name}
                      </div>
                      {skill.description && (
                        <div className="text-[11px] text-[var(--theme-text-secondary)] truncate mt-0.5">
                          {skill.description}
                        </div>
                      )}
                    </div>
                  </button>
                );
              })
            ) : (
              <div className="ppe-skill-dropdown__empty">
                <Sparkles
                  size={20}
                  className="ppe-skill-dropdown__empty-icon"
                />
                <span>{t("skills.noMatchingSkills", "没有匹配的技能")}</span>
              </div>
            )}
            {skillsLoading && displayedSkills.length > 0 && (
              <div className="ppe-skill-dropdown__loading">
                <Loader2 size={14} className="animate-spin" />
                <span>{t("common.loading", "加载中...")}</span>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
