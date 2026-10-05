import {
  getPersonaAvatarIcon,
  isPersonaImageAvatar,
  isEmojiAvatar,
  getEmojiAvatarUrl,
  type PersonaAvatarIconKey,
} from "../../persona/personaAvatar";
import { useTranslation } from "react-i18next";
import { getEmojiAssetUrl } from "../../../utils/emojiAssets";
import { getFullUrl } from "../../../services/api/config";
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
import { ImageWithSkeleton } from "./ImageWithSkeleton";

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

const DEFAULT_AVATAR_EMOJI = "🤖";
const DEFAULT_AVATAR_SRC = getEmojiAssetUrl(DEFAULT_AVATAR_EMOJI, "anim");

export function AssistantAvatar({
  className,
  personaAvatar,
  personaSize = 22,
}: {
  className?: string;
  personaAvatar?: string | null;
  personaSize?: number;
}) {
  const { t } = useTranslation();
  const builtInIcon = getPersonaAvatarIcon(personaAvatar);
  if (builtInIcon) {
    const Icon = ICONS[builtInIcon.key];
    return (
      <div
        className={`overflow-hidden ${className ?? ""}`}
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          background: builtInIcon.bg,
          borderRadius: "50%",
          width: personaSize + 6,
          height: personaSize + 6,
        }}
      >
        <Icon size={personaSize} style={{ color: builtInIcon.color }} />
      </div>
    );
  }

  if (isEmojiAvatar(personaAvatar)) {
    return (
      <ImageWithSkeleton
        src={getEmojiAvatarUrl(personaAvatar)}
        alt={t("chat.assistant", "助手")}
        className={className}
        inline
        loading="eager"
      />
    );
  }

  if (isPersonaImageAvatar(personaAvatar)) {
    return (
      <ImageWithSkeleton
        src={getFullUrl(personaAvatar) ?? personaAvatar}
        alt={t("chat.assistant", "助手")}
        className={className}
        skipUrlResolve
        inline
        loading="eager"
      />
    );
  }

  return (
    <ImageWithSkeleton
      src={DEFAULT_AVATAR_SRC}
      alt={t("chat.assistant", "助手")}
      className={className}
      inline
      loading="eager"
    />
  );
}
