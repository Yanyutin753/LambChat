import { AgentAvatar } from "../common/AgentAvatar";
import { isPersonaImageAvatar } from "./personaAvatar";

export function PersonaAvatarIcon({
  avatar,
  seed,
  primaryTag,
  size = 16,
  className = "",
}: {
  avatar?: string | null;
  seed?: string;
  primaryTag?: string;
  size?: number | string;
  className?: string;
}) {
  return (
    <AgentAvatar
      avatar={avatar}
      seed={seed || primaryTag}
      size={size}
      iconSize={typeof size === "number" ? Math.round(size * 0.6) : 16}
      className={className}
    />
  );
}

export function PersonaAvatarImage({
  avatar,
  alt = "",
  className = "",
}: {
  avatar?: string | null;
  alt?: string;
  className?: string;
}) {
  if (!isPersonaImageAvatar(avatar)) return null;
  return <AgentAvatar avatar={avatar} seed={alt} size="100%" className={className} />;
}
