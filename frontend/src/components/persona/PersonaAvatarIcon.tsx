import { ImageWithSkeleton } from "../chat/ChatMessage/ImageWithSkeleton";
import {
  Code2,
  Database,
  GraduationCap,
  Package,
  PenTool,
  Shield,
  Sparkles,
  Zap,
  type LucideIcon,
} from "lucide-react";
import {
  getPersonaAvatarIcon,
  isPersonaImageAvatar,
  type PersonaAvatarIconKey,
} from "./personaAvatar";
import { getCategoryIcon } from "../panels/MarketplacePanel/constants";
import { getFullUrl } from "../../services/api";

const ICONS: Record<PersonaAvatarIconKey, LucideIcon> = {
  sparkles: Sparkles,
  academic: GraduationCap,
  coding: Code2,
  writing: PenTool,
  security: Shield,
  data: Database,
  productivity: Zap,
  general: Package,
};

export function PersonaAvatarIcon({
  avatar,
  primaryTag,
  size = 16,
  className = "",
}: {
  avatar?: string | null;
  primaryTag?: string;
  size?: number | string;
  className?: string;
}) {
  const builtIn = getPersonaAvatarIcon(avatar);
  if (builtIn) {
    const Icon = ICONS[builtIn.key];
    return (
      <Icon
        size={size}
        className={className}
        style={{ color: builtIn.color }}
      />
    );
  }

  const CategoryIcon =
    avatar && primaryTag ? getCategoryIcon(primaryTag) : null;
  if (CategoryIcon) {
    return <CategoryIcon size={size} className={className} />;
  }

  return (
    <ImageWithSkeleton
      src="/images/illustrations/lamb-avatar.png"
      alt=""
      className={`persona-default-avatar ${className}`}
      skipUrlResolve
      inline
      loading="eager"
      style={{ objectFit: "contain", width: size, height: size }}
      errorFallback={<Sparkles size={size} />}
    />
  );
}

export function PersonaAvatarImage({
  avatar,
  alt = "",
  className = "",
  onLoad,
  onError,
}: {
  avatar?: string | null;
  alt?: string;
  className?: string;
  onLoad?: React.ReactEventHandler<HTMLImageElement>;
  onError?: React.ReactEventHandler<HTMLImageElement>;
}) {
  if (!isPersonaImageAvatar(avatar)) return null;
  const resolvedAvatar = getFullUrl(avatar) ?? avatar;
  return (
    <ImageWithSkeleton
      src={resolvedAvatar}
      alt={alt}
      skipUrlResolve
      inline
      className={className}
      onLoad={
        onLoad
          ? () => onLoad({} as React.SyntheticEvent<HTMLImageElement>)
          : undefined
      }
      onError={
        onError
          ? () => onError({} as React.SyntheticEvent<HTMLImageElement>)
          : undefined
      }
    />
  );
}
