import { useState } from "react";
import type { PersonaPreset } from "../../types";
import {
  PersonaAvatarIcon,
  PersonaAvatarImage,
} from "../persona/PersonaAvatarIcon";
import {
  isEmojiAvatar,
  getEmojiAvatarUrl,
  isPersonaImageAvatar,
} from "../persona/personaAvatar";

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
  const isImage = isPersonaImageAvatar(preset.avatar);
  const emojiAvatar = isEmojiAvatar(preset.avatar) ? preset.avatar : null;
  const isEmoji = !!emojiAvatar;
  const [imgLoaded, setImgLoaded] = useState(false);
  const [imgError, setImgError] = useState(false);

  return (
    <div
      className={className}
      style={style}
      data-avatar-state={
        (isImage || isEmoji) && !imgLoaded && !imgError
          ? "loading"
          : (isImage || isEmoji) && imgLoaded
            ? "loaded"
            : "ready"
      }
    >
      {isEmoji ? (
        !imgError ? (
          <PersonaAvatarImage
            avatar={getEmojiAvatarUrl(emojiAvatar!)}
            alt=""
            className={imgClassName}
            onLoad={() => setImgLoaded(true)}
            onError={() => setImgError(true)}
          />
        ) : (
          <PersonaAvatarIcon
            avatar={null}
            primaryTag={preset.tags?.[0]}
            size={iconSize}
          />
        )
      ) : isImage ? (
        !imgError ? (
          <PersonaAvatarImage
            avatar={preset.avatar}
            alt=""
            className={imgClassName}
            onLoad={() => setImgLoaded(true)}
            onError={() => setImgError(true)}
          />
        ) : (
          <PersonaAvatarIcon
            avatar={null}
            primaryTag={preset.tags?.[0]}
            size={iconSize}
          />
        )
      ) : preset.avatar ? (
        <PersonaAvatarIcon
          avatar={preset.avatar}
          primaryTag={preset.tags?.[0]}
          size={iconSize}
        />
      ) : (
        <PersonaAvatarIcon
          size="100%"
          className={imgClassName || "h-full w-full"}
        />
      )}
    </div>
  );
}
