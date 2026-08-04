import { Ban, Plus } from "lucide-react";
import { useTranslation } from "react-i18next";
import { SkillChip } from "./SkillChip";
import type { SkillResponse } from "../../types";

interface ChatInputRunSkillsBarProps {
  skillNames: string[];
  availableSkills: Array<Pick<SkillResponse, "name" | "tags">>;
  onOpenSelector: () => void;
  onRemoveSkill: (name: string) => void;
  onClear: () => void;
}

export function ChatInputRunSkillsBar({
  skillNames,
  availableSkills,
  onOpenSelector,
  onRemoveSkill,
  onClear,
}: ChatInputRunSkillsBarProps) {
  const { t } = useTranslation();
  if (skillNames.length === 0) return null;

  return (
    <div
      className="group flex flex-wrap items-center gap-2.5 px-2.5 py-2.5 mb-px"
      style={{
        borderBottom:
          "1px solid color-mix(in srgb, var(--theme-border) 50%, transparent)",
      }}
    >
      <div className="skill-chip-row min-w-0 flex-1" style={{ gap: "0.75rem" }}>
        {skillNames.map((skillName) => {
          const skill = availableSkills.find((item) => item.name === skillName);
          return (
            <span key={skillName} className="group">
              <SkillChip
                name={skillName}
                tags={skill?.tags ?? []}
                onClick={onOpenSelector}
                onRemove={() => onRemoveSkill(skillName)}
              />
            </span>
          );
        })}
        <button
          type="button"
          onClick={onOpenSelector}
          className="skill-chip"
          aria-label={t("common.add", "Add")}
          title={t("common.add", "Add")}
          style={{
            opacity: 0.4,
            cursor: "pointer",
          }}
        >
          <Plus size={14} style={{ color: "var(--theme-text-secondary)" }} />
        </button>
      </div>
      <button
        type="button"
        className="shrink-0 transition-colors opacity-0 group-hover:opacity-100 ml-1"
        style={{ color: "var(--theme-text-tertiary)" }}
        onClick={onClear}
        title={t("common.clear", "Clear")}
      >
        <Ban size={12} />
      </button>
    </div>
  );
}
