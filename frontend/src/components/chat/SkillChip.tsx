import { memo } from "react";
import { Sparkles, X } from "lucide-react";
import { getCategoryIcon, nameToGradient } from "../common/cardUtils";

interface SkillChipProps {
  name: string;
  tags?: string[];
  onRemove?: () => void;
  onClick?: () => void;
}

export const SkillChip = memo(function SkillChip({
  name,
  tags,
  onRemove,
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
        onClick={
          onRemove
            ? (e) => {
                e.stopPropagation();
                onRemove();
              }
            : undefined
        }
        role={onRemove ? "button" : undefined}
        tabIndex={onRemove ? 0 : undefined}
        aria-label={onRemove ? `Remove ${name}` : undefined}
        onKeyDown={
          onRemove
            ? (e) => {
                if (e.key === "Enter" || e.key === " ") {
                  e.preventDefault();
                  e.stopPropagation();
                  onRemove();
                }
              }
            : undefined
        }
      >
        {onRemove ? (
          <X size={10} className="text-white" strokeWidth={2.5} />
        ) : (
          <Icon size={10} className="text-white" strokeWidth={2.5} />
        )}
      </span>
      <span className="skill-chip-node-name">{name}</span>
    </span>
  );
});
