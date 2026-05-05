import { useState, useCallback } from "react";
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
  size?: number;
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

  const FallbackIcon = primaryTag ? getCategoryIcon(primaryTag) : Sparkles;
  return <FallbackIcon size={size} className={className} />;
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
  const [loaded, setLoaded] = useState(false);

  const handleLoad = useCallback(
    (e: React.SyntheticEvent<HTMLImageElement>) => {
      setLoaded(true);
      onLoad?.(e);
    },
    [onLoad],
  );

  const handleError = useCallback(
    (e: React.SyntheticEvent<HTMLImageElement>) => {
      setLoaded(true);
      onError?.(e);
    },
    [onError],
  );

  if (!isPersonaImageAvatar(avatar)) return null;
  return (
    <img
      src={avatar}
      alt={alt}
      className={className}
      onLoad={handleLoad}
      onError={handleError}
      style={loaded ? {} : { opacity: 0 }}
    />
  );
}
