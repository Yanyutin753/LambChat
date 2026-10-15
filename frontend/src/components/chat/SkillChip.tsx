import { memo } from "react";
import { AgentAvatar } from "../common/AgentAvatar";

interface SkillChipProps {
  name: string;
  tags?: string[];
  onClick?: () => void;
}

export const SkillChip = memo(function SkillChip({
  name,
  onClick,
}: SkillChipProps) {
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
      <AgentAvatar seed={name} size="1em" className="skill-chip-node-avatar" />
      <span className="skill-chip-node-name font-serif">{name}</span>
    </span>
  );
});
