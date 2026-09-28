import { getEmojiAssetUrl } from "../../utils/emojiAssets";
import { ImageWithSkeleton } from "../chat/ChatMessage/ImageWithSkeleton";

// Legacy default icons → mapped to 💬
const LEGACY_DEFAULT_ICONS = new Set(["MessageCircle", "Bot", "📁"]);

function renderEmojiIcon(
  icon: string,
  size?: number,
  className?: string,
) {
  return (
    <ImageWithSkeleton
      src={getEmojiAssetUrl(icon, "3d")}
      alt={icon}
      className={className}
      inline
      loading="eager"
      style={{
        objectFit: "contain",
        ...(size != null
          ? { width: size, height: size }
          : {}),
      }}
    />
  );
}

// Dynamic icon renderer - all icons rendered as FluentEmoji 3D
export function DynamicIcon({
  name,
  size,
  className,
}: {
  name?: string;
  size?: number;
  className?: string;
}) {
  if (!name || LEGACY_DEFAULT_ICONS.has(name))
    return renderEmojiIcon("💬", size, className);
  // Check if it's an emoji (non-ASCII character, or no ASCII letters)
  const isEmoji = !/^[a-zA-Z]+$/.test(name);
  if (isEmoji) {
    return renderEmojiIcon(name, size, className);
  }
  // Unrecognized ASCII names fall back to 💬
  return renderEmojiIcon("💬", size, className);
}
