import { AgentAvatar } from "../common/AgentAvatar";

interface TeamAvatarProps {
  avatar?: string | null;
  fallbackAvatar?: string | null;
  fallbackTag?: string;
  label?: string;
  className?: string;
  imgClassName?: string;
  iconSize?: number;
  style?: React.CSSProperties;
}

export function TeamAvatar({
  avatar,
  fallbackAvatar,
  fallbackTag,
  label,
  className = "",
  imgClassName = "scb__avatar-img",
  iconSize = 16,
  style,
}: TeamAvatarProps) {
  return (
    <span
      className={["team-avatar", className].filter(Boolean).join(" ")}
      title={label}
      style={{ ...style, borderRadius: "50%" }}
    >
      <AgentAvatar
        avatar={avatar ?? fallbackAvatar}
        seed={label || fallbackTag}
        size="100%"
        iconSize={iconSize}
        className={imgClassName}
      />
    </span>
  );
}
