import { useState } from "react";
import type { PersonaPreset } from "../../types";
import { AgentAvatar } from "../common/AgentAvatar";
import { isPersonaImageAvatar, isEmojiAvatar } from "./personaAvatar";

interface PersonaAvatarWithLoadingProps {
  preset: PersonaPreset;
  className?: string;
  imgClassName?: string;
  iconSize?: number;
  style?: React.CSSProperties;
}

export function PersonaAvatarWithLoading({
  preset,
  className,
  imgClassName,
  iconSize = 14,
  style,
}: PersonaAvatarWithLoadingProps) {
  const [settledAvatar, setSettledAvatar] = useState<string | null>();
  const isImage =
    isPersonaImageAvatar(preset.avatar) || isEmojiAvatar(preset.avatar);
  return (
    <div
      className={className}
      style={{ ...style, borderRadius: "50%" }}
      data-avatar-state={
        isImage && settledAvatar !== preset.avatar ? "loading" : "ready"
      }
    >
      <AgentAvatar
        avatar={preset.avatar}
        seed={preset.id || preset.name}
        size="100%"
        iconSize={iconSize}
        className={imgClassName || "h-full w-full"}
        onLoad={() => setSettledAvatar(preset.avatar)}
        onError={() => setSettledAvatar(preset.avatar)}
      />
    </div>
  );
}
