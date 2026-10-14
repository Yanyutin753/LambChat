import { AgentAvatar } from "../../common/AgentAvatar";

export function AssistantAvatar({
  className,
  personaAvatar,
  personaName,
  personaSeed,
  personaSize = 22,
}: {
  className?: string;
  personaAvatar?: string | null;
  personaName?: string | null;
  personaSeed?: string | null;
  personaSize?: number;
}) {
  return (
    <AgentAvatar
      avatar={personaAvatar}
      seed={personaSeed || personaName || "assistant"}
      size={personaSize}
      className={className}
    />
  );
}
