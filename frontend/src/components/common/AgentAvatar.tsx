import type { ReactNode } from "react";
import Avatar from "boring-avatars";
import type { LucideIcon } from "lucide-react";
import { ImageWithSkeleton } from "../chat/ChatMessage/ImageWithSkeleton";
import { isEmojiAvatar } from "../persona/personaAvatar";
import { getEmojiAssetUrl } from "../../utils/emojiAssets";
import {
  getModelIconUrl,
  isMonochromeIcon,
  modelIconSlugs,
} from "../agent/modelIcon";
import { nameToGradient } from "./cardUtils";

const modelIcons = new Set(modelIconSlugs);
const modelIconUrls = new Set(
  modelIconSlugs.map((slug) => getModelIconUrl(slug, undefined, slug)),
);
const monochromeIconUrls = new Set(
  modelIconSlugs
    .filter((slug) => isMonochromeIcon(slug, slug))
    .map((slug) => getModelIconUrl(slug, undefined, slug)),
);

/** Shared avatar rendering for agents, roles, teams and their pickers. */
export function AgentAvatar({
  avatar,
  seed = "agent",
  size = 20,
  className = "",
  children,
  onLoad,
  onError,
}: {
  avatar?: string | null;
  seed?: string;
  size?: number | string;
  iconSize?: number;
  className?: string;
  fallbackIcon?: LucideIcon;
  children?: ReactNode;
  onLoad?: () => void;
  onError?: () => void;
}) {
  const value = avatar?.trim() || "";
  const generated = value.startsWith("generated:");
  const avatarSeed = generated ? value.slice("generated:".length) || seed : seed;
  const colors = nameToGradient(avatarSeed);
  const frameClassName = `relative inline-flex shrink-0 items-center justify-center overflow-hidden rounded-full ${className}`;
  const frameStyle = {
    width: size,
    height: size,
    borderRadius: "50%",
    background: `color-mix(in srgb, ${colors[0]} 34%, var(--theme-bg-card))`,
    color: "var(--theme-text)",
  };
  const artwork = (
    <span className="agent-avatar__artwork inline-flex h-full w-full">
      <Avatar name={avatarSeed} variant="beam" size="100%" colors={colors} />
    </span>
  );
  const fallback = (
    <span className={frameClassName} style={frameStyle} data-avatar-style="boring" aria-hidden="true">
      {artwork}
    </span>
  );
  if (children) {
    return (
      <span
        className={`${frameClassName} [&>svg]:text-current [&>svg]:stroke-[1.6]`}
        style={frameStyle}
        aria-hidden="true"
      >
        {children}
      </span>
    );
  }
  if (generated) return fallback;

  const slug = value.replace(/^(lobe|lobehub):/i, "").toLowerCase();
  const modelIconUrl = modelIcons.has(slug)
    ? getModelIconUrl(slug, undefined, slug)
    : null;
  const emoji = isEmojiAvatar(value);
  const imageSource = modelIconUrl || (emoji ? getEmojiAssetUrl(value, "3d") : value);
  const isBrandIcon = !!modelIconUrl || modelIconUrls.has(value);
  const monochrome = isBrandIcon && monochromeIconUrls.has(imageSource);
  if (modelIconUrl || emoji || /^(\/|https?:\/\/|data:image\/|blob:)/i.test(value)) {
    return (
      <span className={frameClassName} style={frameStyle} aria-hidden="true">
        <ImageWithSkeleton
          key={value}
          src={imageSource}
          skipUrlResolve={isBrandIcon}
          alt=""
          inline
          loading="eager"
          className={`h-full w-full ${monochrome ? "dark:[&>img]:invert" : ""}`}
          style={{
            width: "100%",
            height: "100%",
            objectFit:
              emoji || isBrandIcon || /\.svg(?:[?#]|$)/i.test(value)
                ? "contain"
                : "cover",
          }}
          errorFallback={
            <span className="absolute inset-0 rounded-full" data-avatar-style="boring">{artwork}</span>
          }
          onLoad={onLoad}
          onError={onError}
        />
      </span>
    );
  }
  return fallback;
}
