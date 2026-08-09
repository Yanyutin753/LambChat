import { memo } from "react";
import { Sparkles } from "lucide-react";
import { getCategoryIcon, nameToGradient } from "../common/cardUtils";

interface SkillChipProps {
  name: string;
  tags?: string[];
  onClick?: () => void;
}

export const SkillChip = memo(function SkillChip({
  name,
  tags,
  onClick,
}: SkillChipProps) {
  const Icon = tags?.[0] ? getCategoryIcon(tags[0]) : Sparkles;
  const [c1, c2] = nameToGradient(name);

  return (
    <span
      className="skill-chip-node"
      role={onClick ? "button" : undefined}
      tabIndex={onClick ? 0 : undefined}
      onClick={onClick}
      onKeyDown={
        onClick
          ? (e) => {
              if (e.key === "Enter" || e.key === " ") {
                e.preventDefault();
                onClick();
              }
            }
          : undefined
      }
      title={name}
    >
      <span
        className="skill-chip-node-avatar"
        style={{
          background: `linear-gradient(135deg, ${c1}, ${c2})`,
        }}
      >
        <Icon size="0.82em" className="text-white" strokeWidth={2.5} />
      </span>
      <span className="skill-chip-node-name">{name}</span>
    </span>
  );
});
