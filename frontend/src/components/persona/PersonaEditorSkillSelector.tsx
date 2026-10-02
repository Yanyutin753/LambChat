import { useCallback, useMemo, useState } from "react";
import { Sparkles } from "lucide-react";
import { useSkills } from "../../hooks/useSkills";
import { PersonaEditorBindingSelector } from "./PersonaEditorBindingSelector";
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
  const [skillSearch, setSkillSearch] = useState("");
  const [skillPage, setSkillPage] = useState(1);
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
    error,
    fetchSkills,
  } = useSkills({
    enabled: open,
    listParams: skillListParams,
    appendPages: true,
  });
  const hasMoreSkills = allSkills.length < totalSkills;
  const handleSkillListScroll = useCallback(
    (event: React.UIEvent<HTMLDivElement>) => {
      if (skillsLoading || error || !hasMoreSkills) return;
      const target = event.currentTarget;
      const distanceToBottom =
        target.scrollHeight - target.scrollTop - target.clientHeight;
      if (distanceToBottom <= 48) setSkillPage((page) => page + 1);
    },
    [hasMoreSkills, skillsLoading, error],
  );
  return (
    <PersonaEditorBindingSelector
      options={allSkills}
      selected={skillNames}
      onChange={onSkillNamesChange}
      open={open}
      onOpenChange={onOpenChange}
      icon={<Sparkles size={12} aria-hidden="true" />}
      countLabelKey="personaPresets.skillCount"
      placeholderKey="personaPresets.skillsInputPlaceholder"
      searchPlaceholderKey="skills.searchSkills"
      emptyKey="skills.noMatchingSkills"
      searchValue={skillSearch}
      onSearchChange={handleSkillSearchChange}
      onScroll={handleSkillListScroll}
      loading={skillsLoading}
      error={!!error}
      onRetry={() => {
        void fetchSkills(skillListParams);
      }}
    />
  );
}
