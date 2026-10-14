import { AgentAvatar } from "../common/AgentAvatar";

export function AgentIcon({
  icon,
  seed,
  size = 20,
  className,
}: {
  icon?: string;
  seed?: string;
  size?: number;
  className?: string;
}) {
  return <AgentAvatar avatar={icon} seed={seed} size={size} className={className} />;
}
