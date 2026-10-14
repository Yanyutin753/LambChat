import { AgentAvatar } from "../../common/AgentAvatar";

export function AssistantAvatar({
  className,
  personaAvatar,
  personaName,
  personaSize = 22,
}: {
  className?: string;
  personaAvatar?: string | null;
  personaName?: string | null;
  personaSize?: number;
}) {
  return (
    <AgentAvatar
      avatar={personaAvatar}
      seed={personaName || "assistant"}
      size={personaSize}
      className={className}
    />
  );
}
